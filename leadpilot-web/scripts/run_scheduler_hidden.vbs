' Starts run_scheduler.cmd with no visible window (window style 0) and waits for it to finish.
Option Explicit
Dim shell, fso, folder, code
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
code = shell.Run("""" & folder & "\run_scheduler.cmd""", 0, True)
WScript.Quit code
