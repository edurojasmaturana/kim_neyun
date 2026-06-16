"""Entry point para AWS Lambda (job batch).

EventBridge Scheduler invoca esta función; ignora el evento y corre el batch
completo. En local se usa `python -m inference.run_batch`.
"""


def handler(event, context):
    from .run_batch import main

    main()
    return {"ok": True}
