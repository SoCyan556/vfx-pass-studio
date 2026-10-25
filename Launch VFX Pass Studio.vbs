Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
launcher = root & "\VFX Pass Studio.exe"
If files.FileExists(launcher) Then
  shell.Run Chr(34) & launcher & Chr(34), 1, False
  WScript.Quit
End If
python = root & "\.venv\Scripts\pythonw.exe"
If Not files.FileExists(python) Then
  MsgBox "Run setup.ps1 first to install the local runtime.", 48, "VFX Pass Studio"
Else
  shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & root & "\app.py" & Chr(34), 1, False
End If
