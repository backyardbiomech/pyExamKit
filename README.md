# pyExamScan installation on Mac
last edited 11 Feb., 2022

1. Download the [Miniconda installer](https://conda.io/miniconda.html) aka miniconda from Continuum. Except in unusual circumstances you’ll want the latest 64bit Python 3.x installer. You can also use the full Anaconda environment, which will let you avoid many of the steps below, though the download is **much** larger and installs many packages not needed for pyExamScan. I recommend you stick with miniconda unless you already use Anaconda. If you use the full Anaconda installer, you can jump down to step 4 below.
  + NOTE: you can also create a conda env and install in there. If you don't know what that means, don't worry about it.
2. To install Miniconda, open a Terminal window. On a mac, hit `cmd-space`, type in "terminal", and hit enter.
    1. In the terminal window, change directory into your downloads folder:  
    `cd ~/Downloads`
    NB: if you don't know, `cd` stands for "change directories", and is like navigating folders. The `~` on a Mac is a shortcut for your home directory – the folder named as your user name that contains your Documents, Downloads, and Desktop folders, and where you'll be installing miniconda. So `~/Downloads` is just a handy shortcut for `Volumes/Macintosh HD/Users/<your user name>/Downloads`
    2. Then install (you might need to change the text to match the name of the file you just downloaded).  
    `bash Miniconda3-latest-MacOSX-x86_64.sh`
    3. Agree to all of the default options.
    4. Close that terminal window, and open a new one.
3. In that window enter the following commands to install the required packages:
    1. `conda update --all`  (this updates all the installed Anaconda packages)
    2. `conda config --add channels conda-forge` (adds the conda-forge package source as the first place to look)
    4. `conda install opencv matplotlib pandas scipy Pillow imageio` (this installs Python packages required by pyExamScan. Agree to install all and their dependencies - it will be a long list and may take a few minutes)
    5. `pip install fpdf` (This installs one package not available directly from Anaconda)
4. Opencv is a finicky package, so before we get too much further, check the installation of opencv. In the terminal:
    1. `python3`
    2. `import cv2`
    3. If you don’t get an error, congrats, opencv is installed. Quit python with `quit()`, and go to step 5.
    4. If you get an error that ends with something like `libopencv_core…dylib, Reason: image not found`:
        1. Quit python with `quit()`
        2. `conda install openblas=0.2.19`
        3. `python3`
        4. `import cv2`
        5. if you don’t get an error, congrats, opencv is installed. Quit python with `quit()`.
5. Now that you have a Python environment with opencv and other packages installed, it's time to install the pyExamScan software:
    1. Go to the [github repo](https://github.com/backyardbiomech/pyExamScan_v2). Click on the green `Code` button, and select `Download zip`. Uncompress the zip in your downloads folder. Make sure the uncompressed folder is named exactly `pyexamscan_v2`, and move it to your Desktop.
6. Open that folder and open the [Usage Instructions](https://github.com/backyardbiomech/pyExamScan_v2/blob/main/Usage_Instructions.md)