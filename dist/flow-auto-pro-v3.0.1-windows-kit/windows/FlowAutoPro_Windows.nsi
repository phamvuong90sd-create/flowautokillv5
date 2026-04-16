; Flow Auto Pro V3.0.1 by blackshop.xyz - Windows Installer (NSIS)
; Build command (on Windows with NSIS installed):
;   makensis FlowAutoPro_Windows.nsi

!include "MUI2.nsh"
!include "nsDialogs.nsh"

Name "Flow Auto Pro V3.0.1 by blackshop.xyz"
OutFile "FlowAutoPro_v3.0.1_Setup.exe"
InstallDir "$PROFILE\.openclaw\flow-auto-pro-kit"
RequestExecutionLevel user

Var LicenseKeyInput
Var LicenseKey
Var GuiCheckbox
Var InstallGui

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
Page custom LicenseKeyPageCreate LicenseKeyPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Function LicenseKeyPageCreate
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "Nhập LICENSE_KEY để kích hoạt Flow Auto Pro:"
  Pop $0

  ${NSD_CreateText} 0 28u 100% 12u ""
  Pop $LicenseKeyInput

  ${NSD_CreateCheckbox} 0 48u 100% 12u "Cài thêm GUI desktop mode (khuyến nghị)"
  Pop $GuiCheckbox
  ${NSD_Check} $GuiCheckbox

  nsDialogs::Show
FunctionEnd

Function LicenseKeyPageLeave
  ${NSD_GetText} $LicenseKeyInput $LicenseKey
  ${NSD_GetState} $GuiCheckbox $InstallGui
  StrCmp $LicenseKey "" 0 +2
    MessageBox MB_ICONEXCLAMATION "LICENSE_KEY không được để trống" /SD IDOK
  StrCmp $LicenseKey "" 0 +2
    Abort
FunctionEnd

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\*.*"

  ; Pass LICENSE_KEY + INSTALL_GUI to PowerShell installer via process env
  StrCpy $0 "n"
  StrCmp $InstallGui "1" 0 +2
  StrCpy $0 "y"
  nsExec::ExecToLog 'cmd /C "set PRESET_LICENSE_KEY=$LicenseKey&& set INSTALL_GUI=$0&& powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\windows\install_windows.ps1""'

  ; Create desktop shortcut to run setup again if needed
  CreateShortcut "$DESKTOP\Flow Auto Pro Setup.lnk" "powershell.exe" "-NoProfile -ExecutionPolicy Bypass -File \"$INSTDIR\windows\install_windows.ps1\""
SectionEnd
