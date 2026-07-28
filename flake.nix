{
  description = "Development shell for Streckenbuch Export";

  # 26.05 is the last supported nixpkgs release for Intel macOS.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python313;
          tkinterdnd2 = python.pkgs.buildPythonPackage rec {
            pname = "tkinterdnd2";
            version = "0.6.2";
            pyproject = true;

            src = pkgs.fetchPypi {
              inherit pname version;
              hash = "sha256-4BXC2GPJKS5h0ClN6kMBD/mcPMlCPlZGduBN9BPemRY=";
            };

            build-system = [ python.pkgs.setuptools ];
            dependencies = [ python.pkgs.tkinter ];
            doCheck = false; # Importing Tk requires a display on some builders.
          };
          pythonEnv = python.withPackages (ps: [
            ps.odfpy
            ps.openpyxl
            ps.pyinstaller
            ps.pypdf
            ps.pytest
            ps.tkinter
            tkinterdnd2
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              pythonEnv
              pkgs.git
              pkgs.gnumake
              pkgs.uv
            ];

            env = {
              # Keep Tk available when uv creates an isolated project venv from
              # the Nix Python interpreter.
              PYTHONPATH = "${python.pkgs.tkinter}/${python.sitePackages}";
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = "${pythonEnv}/bin/python";
            };

            shellHook = ''
              echo ">> Streckenbuch Export development shell"
            '';
          };
        });
    };
}
