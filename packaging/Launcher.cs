using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

internal static class Launcher {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string id);

    [STAThread]
    private static int Main(string[] args) {
        SetCurrentProcessExplicitAppUserModelID("SoCyan.VFXPassStudio");
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
        bool setup = args.Length > 0 && args[0] == "--setup";
        try {
            if (setup || !File.Exists(python) || !File.Exists(Path.Combine(root, ".venv", "studio-ready.txt"))) {
                if (!setup && MessageBox.Show("Install the local AI runtime? This downloads several GB of dependencies. Model weights download when first used.",
                    "VFX Pass Studio", MessageBoxButtons.OKCancel, MessageBoxIcon.Information) != DialogResult.OK) return 0;
                var installer = new ProcessStartInfo("powershell.exe",
                    "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(root, "setup.ps1") + "\" -WaitOnError") {
                    WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = false
                };
                using (var process = Process.Start(installer)) { process.WaitForExit(); if (process.ExitCode != 0) return process.ExitCode; }
            }
            var app = new ProcessStartInfo(python, "\"" + Path.Combine(root, "app.py") + "\"") {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true
            };
            Process.Start(app);
            return 0;
        } catch (Exception e) {
            MessageBox.Show(e.Message + "\nRun Repair runtime from the Start menu to retry setup.", "VFX Pass Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
