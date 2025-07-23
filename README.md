# Round 1A: PDF Outline Extraction

Extracts structured outlines from PDF documents with hierarchical heading detection and 0-based page indexing.

## Features
- ✅0-based page indexing (page 1 = 0)
- ✅Hierarchical heading detection (H1, H2, H3)
- ✅Smart font size and formatting analysis
- ✅Offline processing (no network required)
- ✅Clean text extraction with auto-numbering removal

## Overview
This project is a Python application designed for a hackathon. It encapsulates the core logic of the application within a single script and is containerized using Docker for easy deployment and scalability.

## Approach
This project implements a structured PDF outline extractor designed to identify and extract hierarchical headings (up to H4) from PDF documents. The system uses precise layout-based and textual analysis techniques to detect section titles, ensuring that only true structural headings are included while excluding tables of content, bullet points, and non-heading text. By analyzing font size, boldness, text patterns, and spatial position on the page, the extractor builds a clean and consistent outline that reflects the actual structure of the document. The final output is a JSON representation of the document’s hierarchy, facilitating easy navigation and further downstream processing.

## Project Structure
```
1A/
├── documents            # All sample documents
├── output               # Output for sample PDFs
├── src
│   └── main.py          # Main application script
├── Dockerfile           # Dockerfile for building the application image
├── requirements.txt     # List of Python dependencies
└── README.md            # Documentation for the project
```

## Libraries and Models Used
- Flask: A lightweight WSGI web application framework for Python, used to create the web server.
- Requests: A simple HTTP library for Python, used for making API calls.
- Pandas: A data manipulation and analysis library, used for handling data within the application.

The specific versions of these libraries are listed in the `requirements.txt` file.

## How to Build and Run the Solution
1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd 1A
   ```

2. **Build the Docker image:**
   ```
   docker build -t 1A .
   ```

3. **Run the Docker container:**
   ```
   docker run -v <path-to-your-pdfs>:documents -v <path-to-your-output>:output src/main
   ```

  Replace `<path-to-your-pdfs>` with the path to the directory containing your PDF files, and `<path-to-your-output>` with the directory where the extracted JSON files should be saved.


## Running Locally (without Docker)

Make sure you have Python 3.9+ and all dependencies installed:

1. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

2. **Run the script:**
   ```
   python src/main.py <pdf_file_path> -o <output_dir>
   ```

   Replace `<pdf_file_path>` with the path to the input PDF file, and `<output_dir>` with the path to the desired output directory (e.g., ./output).


## Conclusion
This solution efficiently extracts clean, multi-level outlines from PDFs using formatting and numbering cues, enabling structured navigation and content summarization for real-world and hackathon use cases.