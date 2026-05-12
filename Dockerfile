# Use the official Microsoft Playwright Python image (includes all necessary browser binaries)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the backend server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
