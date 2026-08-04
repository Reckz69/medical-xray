"""Worker — consumes `inference.run` commands and produces scan lifecycle events.

Packages:
    pipeline:  model seam (identity in Sprint 2B, real model in Sprint 3)
    executor:  download -> process -> upload -> persist -> publish
    consumer:  message handlers dispatching to the executor
    main:      RabbitMQ consume loop entrypoint
"""
