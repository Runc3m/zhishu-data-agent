Option Explicit
Dim fs, shell, folder, exe, command
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
exe = folder & "\release\Zhishu\Zhishu.exe"
If fs.FileExists(exe) Then
  command = Chr(34) & exe & Chr(34) & " --data-dir " & Chr(34) & folder & "\storage" & Chr(34)
Else
  exe = folder & "\.venv\Scripts\pythonw.exe"
  If Not fs.FileExists(exe) Then
    MsgBox "Please extract the Windows release package and run Zhishu.exe.", 48, "Zhishu"
    WScript.Quit 1
  End If
  command = Chr(34) & exe & Chr(34) & " " & Chr(34) & folder & "\launcher.py" & Chr(34)
End If
shell.CurrentDirectory = folder
shell.Run command, 1, False
