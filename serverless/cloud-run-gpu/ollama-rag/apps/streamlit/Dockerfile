FROM python:3.12.8-slim-bullseye

RUN apt-get update && apt-get upgrade -y

WORKDIR app/

COPY requirements.txt .

COPY app.py .
 
RUN pip install --no-cache-dir --upgrade -r requirements.txt

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]