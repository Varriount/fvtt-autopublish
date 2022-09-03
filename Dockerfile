# ## Build Stage ## #
FROM python:3-slim AS builder

# Copy application
ADD . /src

# Install dependencies
RUN mkdir /app
RUN pip install /src --target=/app


# ## Package Stage ## # 
FROM gcr.io/distroless/python3-debian10

# Copy files
COPY --from=builder /app /app

# Set runtime parameters
# Working directory will be set to GITHUB_WORKSPACE 
ENV PYTHONPATH /app
ENTRYPOINT ["python3", "-m", "fvtt_autopublish"]
