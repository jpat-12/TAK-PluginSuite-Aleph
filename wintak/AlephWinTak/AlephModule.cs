using Prism.Mef.Modularity;
using Prism.Modularity;
using WinTak.Framework;

namespace AlephWinTak
{
    /// <summary>
    /// Plugin entry point. WinTAK discovers it by MEF in &lt;WinTAK&gt;\Plugins; the button and dock
    /// pane are separate MEF exports, so this module has nothing to wire — it exists so WinTAK
    /// lists and loads the plugin. (IModule and ITakModule share Initialize().)
    /// </summary>
    [ModuleExport(typeof(AlephModule), InitializationMode = InitializationMode.WhenAvailable)]
    public class AlephModule : IModule, ITakModule
    {
        public void Initialize()
        {
        }

        public void Startup()
        {
        }

        public void Terminate()
        {
        }
    }
}
