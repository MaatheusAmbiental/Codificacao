import sys
import os
import site

# This hook is executed at runtime, before the main script.
# Its purpose is to help libraries find their bundled data files.

if hasattr(sys, '_MEIPASS'):
    # 1. Set PROJ_LIB for pyproj/geopandas.
    # This helps pyproj find its data files in the bundled application.
    # The 'pyproj/data' directory is collected by `collect_data_files` in the .spec file
    # and placed inside the bundled app's temporary directory (sys._MEIPASS).
    proj_lib_path = os.path.join(sys._MEIPASS, 'pyproj', 'data')
    if os.path.exists(proj_lib_path):
        os.environ['PROJ_LIB'] = proj_lib_path

    # 2. Add the temporary directory to site-packages.
    # This can help resolve issues with some packages that use pkg_resources
    # or similar mechanisms to find dependencies at runtime.
    site.addsitedir(sys._MEIPASS)
