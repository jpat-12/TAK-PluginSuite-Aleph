using System.Collections.Generic;
using System.ComponentModel.Composition;
using WinTak.Display;
using WinTak.Framework.Docking;
using WinTak.Framework.Docking.Attributes;
using WinTak.Import;
using WinTak.Mapping;
using WinTak.Mapping.Services;

namespace AlephWinTak
{
    /// <summary>
    /// The Aleph Capture pane. WinTAK creates it through MEF and shows <see cref="AlephView"/>
    /// with this pane as its DataContext; all state and behaviour live in <see cref="Model"/>.
    ///
    /// Optional services are imported with AllowDefault so a WinTAK build that lacks one still
    /// loads the pane (that feature just disables itself) instead of failing MEF composition.
    /// </summary>
    [DockPane(Id, "Aleph Capture", Content = typeof(AlephView), DockLocation = DockLocation.Right,
        PreferredWidth = 420, AllowReopenOnRestart = true)]
    internal class AlephDockPane : DockPane
    {
        public const string Id = "AlephWinTak_DockPane";

        public AlephViewModel Model { get; }

        [ImportingConstructor]
        public AlephDockPane(
            IImportManager importManager,
            [ImportMany] IEnumerable<IAreaSelectionOption> areaOptions,
            [Import(AllowDefault = true)] IMapViewController mapView,
            [Import(AllowDefault = true)] IDtedSourcesManager dtedSources)
        {
            Model = new AlephViewModel(importManager, areaOptions, mapView, dtedSources);
        }
    }
}
