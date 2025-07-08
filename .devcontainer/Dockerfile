# Use official Python 3.13 image
FROM python:3.13.5-slim-bookworm

# Update system packages to reduce vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Suppress root-user pip warning
ENV PIP_DISABLE_ROOT_WARNING=1

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy and install your test dependencies
COPY requirements_test.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# (Optional) Create and switch to a non-root user
RUN useradd --create-home devuser
USER devuser

# Set up workspace
WORKDIR /workspace

# Ensure pytest colors & locale
ENV NO_COLOR=yes_please
ENV LANG=C.UTF-8

# Default command: run pytest
CMD ["pytest", "--maxfail=1", "--disable-warnings", "-q", "tests/"]
