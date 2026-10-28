{ pkgs ? import <nixpkgs> { } }:
pkgs.mkShell {
  packages = with pkgs; [
    gcc gnumake docker-client git rsync pkg-config systemd.dev udev libusb1 libusb1.dev
    (python311.withPackages (ps: with ps; [ pyqt5 pytest pytest-qt pip virtualenv ]))
  ];
  # nixpkgs PyQt5 does not set the Qt plugin path outside wrapped apps
  QT_PLUGIN_PATH = "${pkgs.qt5.qtbase}/${pkgs.qt5.qtbase.qtPluginPrefix}";
}
