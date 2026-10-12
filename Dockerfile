FROM python:3.12-slim

WORKDIR /app

COPY one_piece_capitulo.py baixar_capitulo.py servidor.py telegram.py ./

EXPOSE 8000

CMD ["python", "servidor.py"]