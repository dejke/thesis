FROM python:3.11-slim
RUN apt-get update && apt-get install -y iputils-ping
RUN echo "super secret string" > secret.txt
CMD ["python3", "-m", "http.server", "8080"]

