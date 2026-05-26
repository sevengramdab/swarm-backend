' SimplePod Swarm Launcher
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

projectRoot = "D:\vs code project files\outputs\simplepod_swarm"
pythonExe = projectRoot & "\.venv\Scripts\python.exe"
backendUrl = "http://localhost:8000"
shadowUrl = "http://localhost:8002"

' Create logs folder
logPath = projectRoot & "\logs"
If Not FSO.FolderExists(logPath) Then
    FSO.CreateFolder(logPath)
End If

WScript.Echo "SimplePod Swarm Launcher"
WScript.Echo "========================"
WScript.Echo ""

' Start main backend
WScript.Echo "[1/3] Starting Main Backend on port 8000..."
backendCmd = "cmd /c cd /d " & Chr(34) & projectRoot & Chr(34) & " && " & Chr(34) & pythonExe & Chr(34) & " -m uvicorn interfaces.web_ui.backend.main:app --host 0.0.0.0 --port 8000 > " & Chr(34) & logPath & "\backend.log" & Chr(34) & " 2>&1"
WshShell.Run backendCmd, 0, False

' Wait for backend
WScript.Sleep 6000

' Start shadow node
WScript.Echo "[2/3] Starting Shadow PC Node on port 8002..."
shadowCmd = "cmd /c cd /d " & Chr(34) & projectRoot & Chr(34) & " && " & Chr(34) & pythonExe & Chr(34) & " shadow_node.py > " & Chr(34) & logPath & "\shadow.log" & Chr(34) & " 2>&1"
WshShell.Run shadowCmd, 0, False

' Wait for shadow
WScript.Sleep 4000

' Open browser
WScript.Echo "[3/3] Opening Dashboard..."
WshShell.Run "explorer " & Chr(34) & backendUrl & Chr(34), 0, False

WScript.Echo ""
WScript.Echo "========================"
WScript.Echo "SimplePod Swarm is running!"
WScript.Echo "========================"
WScript.Echo ""
WScript.Echo "Dashboard: " & backendUrl
WScript.Echo "API Docs:  " & backendUrl & "/docs"
WScript.Echo "Mesh:      " & backendUrl & "/mesh"
WScript.Echo ""
WScript.Echo "Close this window to exit (services keep running)."
WScript.Sleep 30000
