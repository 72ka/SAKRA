; Inno Setup 6 – instalátor SAKRA pro Windows (x64). Nejdřív sestavit dist\SAKRA (sestav_windows.bat).
; verze jde zadat zvenku (ISCC /DVerze=…, automatické sestavení na GitHubu)
#ifndef Verze
  #define Verze "0.3.0a2"
#endif

[Setup]
AppId={{6E4B7D1A-2C9F-4D1E-9B6A-5A8C3F0D2E71}
AppName=SAKRA
AppVersion={#Verze}
AppPublisher=Jan Heřman (72ka)
AppPublisherURL=https://www.herniarchiv.cz
AppCopyright=© 2025–2026 Jan Heřman, alias 72ka
; licence se ukáže při instalaci (PolyForm Noncommercial 1.0.0; komerční použití jen se souhlasem autora)
LicenseFile=..\NOTICE.txt
AppComments=a Swiss Army Knife for Retrogaming Archaeologists. Digitalizace a archivace audiokazet s programy pro staré počítače. Vyrobeno pro potřeby Herního archivu (www.herniarchiv.cz).
DefaultDirName={autopf}\SAKRA
DefaultGroupName=SAKRA
OutputDir=..\dist
OutputBaseFilename=SAKRA-{#Verze}-instalace
SetupIconFile=sakra.ico
UninstallDisplayIcon={app}\SAKRA.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
WizardStyle=modern

[Languages]
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "plocha"; Description: "Zástupce na ploše"; Flags: unchecked
Name: "asociace"; Description: "Otevírat projekty .sakra v aplikaci SAKRA"

[Files]
Source: "..\dist\SAKRA\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\SAKRA"; Filename: "{app}\SAKRA.exe"
Name: "{group}\Návod SAKRA (PDF)"; Filename: "{app}\_internal\sakra\dokumenty\SAKRA-navod.pdf"
Name: "{group}\Licence SAKRA"; Filename: "{app}\_internal\NOTICE.txt"
Name: "{group}\Odinstalovat SAKRA"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SAKRA"; Filename: "{app}\SAKRA.exe"; Tasks: plocha

[Registry]
Root: HKA; Subkey: "Software\Classes\.sakra"; ValueType: string; ValueName: ""; ValueData: "SAKRA.Projekt"; Flags: uninsdeletevalue; Tasks: asociace
Root: HKA; Subkey: "Software\Classes\SAKRA.Projekt"; ValueType: string; ValueName: ""; ValueData: "Projekt SAKRA"; Flags: uninsdeletekey; Tasks: asociace
Root: HKA; Subkey: "Software\Classes\SAKRA.Projekt\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\SAKRA.exe,0"; Tasks: asociace
Root: HKA; Subkey: "Software\Classes\SAKRA.Projekt\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\SAKRA.exe"" ""%1"""; Tasks: asociace

[Run]
Filename: "{app}\SAKRA.exe"; Description: "Spustit SAKRA"; Flags: nowait postinstall skipifsilent
