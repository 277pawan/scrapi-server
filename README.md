# Advance Web Crawler - Setup Guide

## Prerequisites

Make sure you have **Python 3.14 or higher** installed.

Check your Python version:

```bash
python --version
```

or

```bash
python3 --version
```

---

## Step 1: Install UV

First, verify whether `uv` is installed:

```bash
uv --version
```

If `uv` is not installed, install it using:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Step 2: Clone the Repository

Clone the project repository:

```bash
git clone https://github.com/Abhisheksati1/Advance-Web-Crawler.git .
```

---

## Step 3: Navigate to the Project Directory

```bash
cd <project-directory>
```

Example:

```bash
cd Advance-Web-Crawler
```

---

## Step 4: Initialize UV

Run the following command:

```bash
uv init
```

---

## Step 5: Install Dependencies

Install all required packages:

```bash
uv add -r requirements.txt
```

---

## Step6: Install Playwright

```bash
playwright install-deps
playwright install
```
---

# Running the Project

Follow these steps to run the application after the initial setup is complete:

### 1. Open your terminal
Make sure you are in the project's root directory:
```bash
cd <project-directory>
```

### 2. Activate the correct Virtual Environment
Activate the environment where all dependencies are installed (`venv`):

**Linux / macOS**
```bash
source venv/bin/activate
```

**Windows**
```bash
venv\Scripts\activate
```

### 3. Run the Application
Start the FastAPI server using `uvicorn`:
```bash
uvicorn main:app --reload --port 8001
```

### 4. Access the Application
Once it's running, open your web browser and navigate to:
[http://127.0.0.1:8001/](http://127.0.0.1:8001/)

---

# Tech Stack

- Python 3.14+
- FastAPI
- Uvicorn
- UV Package Manager