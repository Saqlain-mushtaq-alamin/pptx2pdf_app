PPTX → PDF Drag-and-Drop Converter (runs locally on your Windows PC)
=====================================================================

WHAT THIS IS
------------
A small local web app. You open it in your browser, drag in your .pptx
files, click Convert, and it downloads a ZIP of the converted PDFs.
No files are uploaded to the internet — everything happens on your
own computer.


REQUIREMENTS
------------
1. Python 3.8+ installed (https://www.python.org/downloads/)
   - During install, check "Add Python to PATH"

2. LibreOffice installed (free)
   - https://www.libreoffice.org/download/
   - Default install path is usually:
     C:\Program Files\LibreOffice\program\soffice.exe
   - If yours is installed somewhere else, open app.py and edit the
     POSSIBLE_SOFFICE_PATHS list near the top to add your path.

3. Flask (Python package)
   Open Command Prompt and run:
       pip install flask


HOW TO RUN
----------
1. Open Command Prompt (or PowerShell)
2. Navigate to this folder, e.g.:
       cd C:\Users\YourName\Downloads\pptx2pdf_app
3. Run:
       python app.py
4. You should see:
       Using LibreOffice at: C:\Program Files\LibreOffice\program\soffice.exe
       Open http://127.0.0.1:5000 in your browser
5. Open your browser and go to:
       http://127.0.0.1:5000
6. Drag and drop your .pptx files into the box, click "Convert to PDF"
7. A ZIP file with all converted PDFs will download automatically.


TO STOP THE APP
----------------
Go back to the Command Prompt window and press Ctrl + C.


TROUBLESHOOTING
----------------
- "soffice not found" / conversion fails immediately:
    LibreOffice isn't installed, or it's installed at a different path.
    Edit POSSIBLE_SOFFICE_PATHS in app.py and add the correct path to
    soffice.exe on your machine.

- Conversion takes a while the first time:
    Normal — LibreOffice initializes a profile on first run.

- Port 5000 already in use:
    Close other apps using that port, or edit app.py's last line
    (app.run(...)) to use a different port, e.g. port=5050, then visit
    http://127.0.0.1:5050 instead.


FOLDER STRUCTURE
-----------------
pptx2pdf_app/
├── app.py                 <- backend server (run this)
├── templates/
│   └── index.html         <- the frontend page
└── README.txt             <- this file
