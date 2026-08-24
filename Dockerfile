FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# ipmitool is the actual IPMI transport; the MCP server shells out to it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ipmitool \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies + package installation.
COPY pyproject.toml README.md LICENSE ./
COPY ipmi_mcp ./ipmi_mcp
RUN pip install .

# MCP transport = stdio: the client launches the container with -i.
ENTRYPOINT ["python", "-m", "ipmi_mcp"]
