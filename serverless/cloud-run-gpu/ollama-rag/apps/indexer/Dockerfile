FROM python:3.12.8-slim-bullseye

RUN apt-get update && apt-get upgrade -y

WORKDIR app/

COPY requirements.txt .

COPY indexer.py .
 
RUN pip install --no-cache-dir --upgrade -r requirements.txt

CMD ["python", "indexer.py"]

#ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]