using System.Windows;
using System.Windows.Controls;

namespace AlephWinTak
{
    public partial class AlephView : UserControl
    {
        public AlephView()
        {
            InitializeComponent();
        }

        // WPF can't bind PasswordBox.Password (by design), so hand it to the model as typed.
        private void OnTokenChanged(object sender, RoutedEventArgs e)
        {
            if (DataContext is AlephDockPane pane) pane.Model.TokenInput = TokenBox.Password;
        }
    }
}
