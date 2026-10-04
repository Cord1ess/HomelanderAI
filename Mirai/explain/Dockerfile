# The mammogram heatmap: the authors' own Mirai image, plus one small server.
# Same model, weights and preprocessing as the `mirai` service; built FROM the
# same pinned tag so the two can never disagree about which Mirai they run.
FROM mitjclinic/mirai:v0.14.1

COPY explain_server.py /app/explain/explain_server.py
WORKDIR /app/ark
EXPOSE 5001

# One request at a time: a heatmap holds four full-resolution views in memory.
ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:5001", "--timeout", "0", "--threads", "1", \
            "--chdir", "/app/explain", "explain_server:app"]
