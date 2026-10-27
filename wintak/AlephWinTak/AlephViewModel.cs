using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Input;
using System.Windows.Threading;
using AlephWinTak.Core;
using Newtonsoft.Json.Linq;
using WinTak.Display;
using WinTak.Graphics;
using WinTak.Import;
using WinTak.Mapping;
using WinTak.Mapping.Services;

namespace AlephWinTak
{
    /// <summary>
    /// Settings → area → layers → estimate → capture → download &amp; import, plus point lookup.
    /// Same flow as the ATAK and CloudTAK clients; HTTP, DTED merge and area math live in Core/.
    /// Everything here runs on the WPF UI thread; awaits inside Core don't capture it.
    /// </summary>
    public sealed class AlephViewModel : INotifyPropertyChanged
    {
        private static readonly string DtedRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "WinTAK", "DTED");
        private static readonly string DownloadDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AlephWinTak", "packages");
        private static readonly (string Key, string Label)[] LayerLabels =
        {
            ("imagery", "Imagery (MBTiles)"), ("elevation", "Elevation (DTED)"),
            ("osm", "Roads, trails, buildings (KMZ)"), ("photos", "Street-level photos"),
        };

        private readonly IImportManager _import;
        private readonly IMapViewController _mapView;
        private readonly IDtedSourcesManager _dtedSources;
        private readonly AlephSettings _settings = new AlephSettings();
        private readonly AlephClient _client;
        private readonly DispatcherTimer _poll;
        private ServerInfo _info;
        private List<(double Lon, double Lat)> _area;
        private bool _busyDownloading;

        public AlephViewModel(IImportManager import, IEnumerable<IAreaSelectionOption> areaOptions,
                              IMapViewController mapView, IDtedSourcesManager dtedSources)
        {
            _import = import;
            _mapView = mapView;
            _dtedSources = dtedSources;
            _client = new AlephClient(() => _settings.ServerUrl, () => _settings.Token);
            ServerUrl = _settings.ServerUrl;
            AreaOptions = new ObservableCollection<AreaOptionItem>(
                (areaOptions ?? Enumerable.Empty<IAreaSelectionOption>()).Select(o => new AreaOptionItem(o, this)));
            ConnectCommand = new RelayCommand(_ => Connect());
            CaptureCommand = new RelayCommand(_ => Capture(), _ => CanCapture);
            PointCommand = new RelayCommand(_ => PickPoint(), _ => _mapView != null);
            _poll = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
            _poll.Tick += (s, e) => { if (Jobs.Any(j => j.Job.IsActive)) RefreshJobs(); };
            if (_settings.IsConfigured) Connect();
        }

        // --- bindable state ------------------------------------------------------------------

        public string ServerUrl { get => _serverUrl; set => Set(ref _serverUrl, value); }
        private string _serverUrl = "";
        /// <summary>Set from the view's PasswordBox (WPF can't bind one).</summary>
        public string TokenInput { get; set; }
        public bool HasSavedToken => _settings.Token.Length > 0;
        public string Status { get => _status; private set => Set(ref _status, value); }
        private string _status = "Enter the Aleph server URL and your token, then Connect.";
        public bool Connected { get => _connected; private set => Set(ref _connected, value); }
        private bool _connected;
        public string AreaLabel { get => _areaLabel; private set => Set(ref _areaLabel, value); }
        private string _areaLabel = "No area selected.";
        public string EstimateLabel { get => _estimateLabel; private set => Set(ref _estimateLabel, value); }
        private string _estimateLabel = "";
        public string CaptureName { get; set; } = "";
        public string PointResult { get => _pointResult; private set => Set(ref _pointResult, value); }
        private string _pointResult = "";
        public ObservableCollection<AreaOptionItem> AreaOptions { get; }
        public ObservableCollection<LayerItem> Layers { get; } = new ObservableCollection<LayerItem>();
        public ObservableCollection<ZoomItem> Zooms { get; } = new ObservableCollection<ZoomItem>();
        public ZoomItem SelectedZoom { get => _zoom; set { Set(ref _zoom, value); RefreshEstimate(); } }
        private ZoomItem _zoom;
        public ObservableCollection<JobItem> Jobs { get; } = new ObservableCollection<JobItem>();
        private bool _allowed = true;
        private bool CanCapture => Connected && _area != null && Layers.Any(l => l.Selected) && _allowed;

        public ICommand ConnectCommand { get; }
        public ICommand CaptureCommand { get; }
        public ICommand PointCommand { get; }

        // --- actions -------------------------------------------------------------------------

        /// <summary>Run an async action and surface any failure in the status line (never silently).</summary>
        private async void Run(string what, Func<Task> action)
        {
            try
            {
                await action();
            }
            catch (Exception e)
            {
                Status = $"{what} failed: {e.Message}";
            }
        }

        private void Connect()
        {
            Run("Connect", async () =>
            {
                if (!string.IsNullOrWhiteSpace(TokenInput) || ServerUrl != _settings.ServerUrl)
                    _settings.Save(ServerUrl, string.IsNullOrWhiteSpace(TokenInput) ? _settings.Token : TokenInput);
                ServerUrl = _settings.ServerUrl;
                OnPropertyChanged(nameof(HasSavedToken));
                if (!_settings.IsConfigured)
                {
                    Status = "Enter the Aleph server URL and your token, then Connect.";
                    return;
                }
                Status = "Connecting…";
                var info = await _client.InfoAsync();
                var jobs = await _client.JobsAsync();  // also proves the token works
                if (!info.Compatible)
                {
                    Status = $"Server speaks Aleph API v{info.ApiVersion}; this plugin needs v{Api.SupportedApi}. Update one of them.";
                    return;
                }
                _info = info;
                Connected = true;
                Status = string.Format(CultureInfo.InvariantCulture, "Connected · Aleph {0} · up to {1:0} km² · kept {2} h",
                    info.Version, info.MaxAreaKm2, info.TtlHours);
                Layers.Clear();
                foreach (var (key, label) in LayerLabels.Where(l => info.Layers.Contains(l.Key)))
                    Layers.Add(new LayerItem(key, label, key != "photos", RefreshEstimate));
                Zooms.Clear();
                for (int z = 15; z <= Math.Min(19, info.ImageryMaxZoom); z++)
                    Zooms.Add(new ZoomItem(z));
                _zoom = Zooms.FirstOrDefault(z => z.Zoom == info.DefaultZoom) ?? Zooms.LastOrDefault();
                OnPropertyChanged(nameof(SelectedZoom));
                ShowJobs(jobs);
                _poll.Start();
            });
        }

        internal void SelectArea(IAreaSelectionOption option)
        {
            Run("Area selection", async () =>
            {
                Status = $"{option.Title}: draw or pick on the map…";
                VectorMapItemBase shape;
                try
                {
                    shape = await option.SelectAreaAsync();
                }
                catch (OperationCanceledException)
                {
                    Status = "Area selection cancelled.";
                    return;
                }
                if (shape == null)
                {
                    Status = "Area selection cancelled.";
                    return;
                }
                if (!(shape is PolylineBase outline) || outline.Points.Count < 3)
                {
                    option.CancelSelection();
                    Status = "That shape has no outline to capture — use a rectangle or polygon.";
                    return;
                }
                _area = AreaMath.Normalize(outline.Points.Select(p => (p.Longitude, p.Latitude)));
                option.FinalizeSelection();
                double km2 = AreaMath.AreaKm2(_area);
                AreaLabel = string.Format(CultureInfo.InvariantCulture, "{0} · {1:0.00} km² (limit {2:0} km²)",
                    string.IsNullOrEmpty(shape.Name) ? option.Title : shape.Name, km2, _info?.MaxAreaKm2 ?? 0);
                Status = Connected ? Status : "Area selected — connect to estimate.";
                RefreshEstimate();
            });
        }

        private JObject CaptureRequest()
        {
            if (_area == null || _info == null) return null;
            var layers = new JArray(Layers.Where(l => l.Selected).Select(l => l.Key));
            if (layers.Count == 0) return null;
            var request = new JObject { ["area"] = AreaMath.ToGeoJson(_area), ["layers"] = layers };
            if (SelectedZoom != null) request["options"] = new JObject { ["imagery_zoom"] = SelectedZoom.Zoom };
            if (!string.IsNullOrWhiteSpace(CaptureName)) request["name"] = CaptureName.Trim();
            return request;
        }

        private void RefreshEstimate()
        {
            var request = CaptureRequest();
            if (request == null)
            {
                EstimateLabel = "";
                CommandManager.InvalidateRequerySuggested();
                return;
            }
            Run("Estimate", async () =>
            {
                var e = await _client.EstimateAsync(request);
                _allowed = e.Allowed;
                EstimateLabel = string.Format(CultureInfo.InvariantCulture, "≈ {0:0.0} MB package · ~{1} min{2}",
                    e.Bytes / 1e6, Math.Max(1, e.Seconds / 60), e.Allowed ? "" : " — area too large");
                CommandManager.InvalidateRequerySuggested();
            });
        }

        private void Capture()
        {
            var request = CaptureRequest();
            if (request == null) return;
            Run("Capture", async () =>
            {
                var job = await _client.CreateAsync(request);
                Status = "Capture started: " + job.Name;
                await RefreshJobsAsync();
            });
        }

        private void RefreshJobs() => Run("Refresh", RefreshJobsAsync);

        private async Task RefreshJobsAsync() => ShowJobs(await _client.JobsAsync());

        private void ShowJobs(IEnumerable<Job> jobs)
        {
            Jobs.Clear();
            foreach (var job in jobs) Jobs.Add(new JobItem(job, this));
        }

        internal void Retry(Job job) => Run("Retry", async () => { await _client.RetryAsync(job.Id); await RefreshJobsAsync(); });

        internal void Delete(Job job) => Run("Delete", async () => { await _client.DeleteAsync(job.Id); await RefreshJobsAsync(); });

        internal void DownloadAndImport(Job job)
        {
            if (_busyDownloading)
            {
                Status = "A download is already running.";
                return;
            }
            Run("Download", async () =>
            {
                _busyDownloading = true;
                try
                {
                    var progress = new Progress<(long Done, long Total)>(p =>
                        Status = string.Format(CultureInfo.InvariantCulture, "Downloading {0}: {1:0.0} / {2:0.0} MB", job.Name, p.Done / 1e6, p.Total / 1e6));
                    string package = await _client.DownloadPackageAsync(job, DownloadDir, progress, CancellationToken.None);
                    // DTED first, merged into WinTAK's store (fills voids only — see DtedCell).
                    var dted = await Task.Run(() => DtedInstaller.Install(package, DtedRoot));
                    if (dted.Added + dted.Merged > 0) _dtedSources?.RegisterDtedSources();
                    // Then WinTAK's own data-package import for imagery, KMZ and photo markers; the
                    // manifest marks the DTED zip and GIS GeoTIFF ignore="true", so it skips them.
                    await _import.ImportAsync(package, null);
                    Status = $"Imported {job.Name}. Elevation: {dted.Added} new cell(s), {dted.Merged} merged, {dted.Skipped} left as-is.";
                }
                finally
                {
                    _busyDownloading = false;
                }
            });
        }

        private MapMouseEventHandler _pointHandler;

        private void PickPoint()
        {
            if (!Connected)
            {
                Status = "Connect to an Aleph server first.";
                return;
            }
            if (_pointHandler != null) return;  // already waiting for a click
            PointResult = "Click a spot on the map…";
            _pointHandler = (sender, e) =>
            {
                _mapView.MapClick -= _pointHandler;
                _pointHandler = null;
                e.Handled = true;
                var at = e.WorldLocation;
                Run("Point lookup", async () =>
                {
                    PointResult = "Looking up…";
                    var r = await _client.PointAsync(at.Latitude, at.Longitude);
                    var text = string.Format(CultureInfo.InvariantCulture, "{0:0.00000}, {1:0.00000}", at.Latitude, at.Longitude);
                    if (r["elevation_m"]?.Type == JTokenType.Float || r["elevation_m"]?.Type == JTokenType.Integer)
                    {
                        double m = (double)r["elevation_m"];
                        text += string.Format(CultureInfo.InvariantCulture, "\nElevation {0:0} m ({1:0} ft)", m, m * 3.28084);
                    }
                    if (r["address"] is JObject address) text += "\nNear " + (string)address["label"];
                    if (r["photos"] is JArray photos) text += $"\n{photos.Count} street-level photo(s) within 150 m";
                    PointResult = text;
                });
            };
            _mapView.MapClick += _pointHandler;
        }

        // --- INotifyPropertyChanged ------------------------------------------------------------

        public event PropertyChangedEventHandler PropertyChanged;

        private void OnPropertyChanged([CallerMemberName] string name = null) =>
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

        private void Set<T>(ref T field, T value, [CallerMemberName] string name = null)
        {
            if (EqualityComparer<T>.Default.Equals(field, value)) return;
            field = value;
            OnPropertyChanged(name);
        }
    }

    public sealed class AreaOptionItem
    {
        public string Title { get; }
        public ICommand Select { get; }

        internal AreaOptionItem(IAreaSelectionOption option, AlephViewModel owner)
        {
            Title = option.Title;
            Select = new RelayCommand(_ => owner.SelectArea(option));
        }
    }

    public sealed class LayerItem : INotifyPropertyChanged
    {
        private readonly Action _changed;
        private bool _selected;
        public string Key { get; }
        public string Label { get; }

        public bool Selected
        {
            get => _selected;
            set
            {
                _selected = value;
                PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Selected)));
                _changed();
            }
        }

        internal LayerItem(string key, string label, bool selected, Action changed)
        {
            Key = key;
            Label = label;
            _selected = selected;
            _changed = changed;
        }

        public event PropertyChangedEventHandler PropertyChanged;
    }

    public sealed class ZoomItem
    {
        public int Zoom { get; }

        // Ground resolution at ~40°N (cos ≈ 0.77), close enough for the contiguous US.
        public string Label => string.Format(CultureInfo.InvariantCulture, "z{0} (~{1:0.0} m)", Zoom, 156543.03 * 0.77 / Math.Pow(2, Zoom));

        internal ZoomItem(int zoom) => Zoom = zoom;
    }

    public sealed class JobItem
    {
        public Job Job { get; }
        public string Title => string.Format(CultureInfo.InvariantCulture, "{0} · {1} · {2:0.00} km²", Job.Name, Job.State, Job.AreaKm2);
        public string Detail
        {
            get
            {
                var lines = new List<string>();
                if (Job.IsActive) lines.Add(string.Format(CultureInfo.InvariantCulture, "{0:0}% {1}", Job.Percent, Job.Phase));
                lines.AddRange(Job.Warnings.Select(w => "⚠ " + w));
                lines.AddRange(Job.LayerErrors.Select(e => "✗ " + e));
                if (Job.Error != null) lines.Add("✗ " + Job.Error);
                return string.Join("\n", lines);
            }
        }
        public bool HasDetail => Detail.Length > 0;
        public string DownloadLabel => string.Format(CultureInfo.InvariantCulture, "Download & import ({0:0.0} MB)", Job.PackageBytes / 1e6);
        public bool CanDownload => Job.IsComplete;
        public bool CanRetry => Job.CanRetry;
        public string DeleteLabel => Job.IsActive ? "Cancel" : "Delete";
        public ICommand Download { get; }
        public ICommand RetryCommand { get; }
        public ICommand DeleteCommand { get; }

        internal JobItem(Job job, AlephViewModel owner)
        {
            Job = job;
            Download = new RelayCommand(_ => owner.DownloadAndImport(job));
            RetryCommand = new RelayCommand(_ => owner.Retry(job));
            DeleteCommand = new RelayCommand(_ => owner.Delete(job));
        }
    }

    public sealed class RelayCommand : ICommand
    {
        private readonly Action<object> _execute;
        private readonly Func<object, bool> _canExecute;

        public RelayCommand(Action<object> execute, Func<object, bool> canExecute = null)
        {
            _execute = execute;
            _canExecute = canExecute;
        }

        public bool CanExecute(object parameter) => _canExecute?.Invoke(parameter) ?? true;
        public void Execute(object parameter) => _execute(parameter);

        public event EventHandler CanExecuteChanged
        {
            add => CommandManager.RequerySuggested += value;
            remove => CommandManager.RequerySuggested -= value;
        }
    }
}
