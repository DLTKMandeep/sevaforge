FROM ubuntu:22.04
WORKDIR /app
COPY . .
EXPOSE 9001
CMD ["./start.sh"]
