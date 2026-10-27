using System.ComponentModel.Composition;
using WinTak.Framework.Docking;
using WinTak.Framework.Tools;
using WinTak.Framework.Tools.Attributes;

namespace AlephWinTak
{
    /// <summary>Home → Tools ribbon button; opens the Aleph Capture pane.</summary>
    [Button("AlephWinTak_Button", "Aleph Capture",
        Tab = "HomeTab", TabGroup = "ToolsTabGroup", Priority = 90,
        ToolTip = "Capture an area as an offline data package (imagery, DTED, OSM)",
        SmallImage = "pack://application:,,,/AlephWinTak;component/Assets/aleph_24.png",
        LargeImage = "pack://application:,,,/AlephWinTak;component/Assets/aleph_48.png")]
    internal class AlephButton : Button
    {
        private readonly IDockingManager _docking;

        [ImportingConstructor]
        public AlephButton(IDockingManager docking)
        {
            _docking = docking;
        }

        protected override void OnClick()
        {
            _docking.GetDockPane(AlephDockPane.Id)?.Activate();
        }
    }
}
