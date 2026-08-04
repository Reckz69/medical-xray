"""Worker — consumes `inference.run` commands and produces scan lifecycle events.

Packages:
    converters:  CommonImage decode (PNG/JPEG/DICOM)
    preprocess:  tiling + Canny flat-tissue noise variance
    model_manager: ModelManager load-once lifecycle (ADR-006)
    inference:   tiled threaded U-Net predict
    postprocess: CLAHE + unsharp mask + PNG encode
    orchestrator: full pipeline coordinator (ADR-008)
    executor:    download -> process -> upload -> persist -> publish
    consumer:    message handlers dispatching to the executor
    main:        RabbitMQ consume loop entrypoint
"""
