# Copyright (c) Microsoft. All rights reserved.

"""File-based AttachmentStore implementation for ChatKit.

This module provides a simple AttachmentStore implementation that stores
uploaded files on the local filesystem. In production, you should use
cloud storage like S3, Azure Blob Storage, or Google Cloud Storage.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from chatkit.store import AttachmentStore, Store
from chatkit.types import Attachment, AttachmentCreateParams, AttachmentUploadDescriptor, FileAttachment, ImageAttachment
from pydantic import AnyUrl


class AttachmentHandler(AttachmentStore[dict[str, Any]]):
    

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        metadata_store: Store[dict[str, Any]] | None = None
    ):
        """Initialize the file-based attachment store.

        Args:
            uploads_dir: Directory where uploaded files will be stored
            base_url: Base URL for generating upload and preview URLs
            data_store: Optional data store to persist attachment metadata
        """
     
        self.base_url = base_url.rstrip("/")
        self.metadata_store = metadata_store



    async def create_attachment(self, input: AttachmentCreateParams, context: dict[str, Any]) -> Attachment:
        """Create an attachment with upload URL for two-phase upload.

        This creates the attachment metadata and returns upload URLs that
        the client will use to POST the actual file bytes.
        """
        # Generate unique ID for this attachment
        attachment_id = self.generate_attachment_id(input.mime_type, context)

        # Generate upload URL that points to our FastAPI upload endpoint
        upload_url = f"{self.base_url}/upload/{attachment_id}"

        # Create appropriate attachment type based on MIME type
        if input.mime_type.startswith("image/"):
            # For images, also provide a preview URL
            preview_url = f"{self.base_url}/preview/{attachment_id}"

            attachment = ImageAttachment(
                id=attachment_id,
                type="image",
                mime_type=input.mime_type,
                name=input.name,
                upload_descriptor=AttachmentUploadDescriptor(url=AnyUrl(upload_url), method="POST"),
                preview_url=AnyUrl(preview_url),
            )
        else:
            # For files, just provide upload URL
            attachment = FileAttachment(
                id=attachment_id,
                type="file",
                mime_type=input.mime_type,
                name=input.name,
                upload_descriptor=AttachmentUploadDescriptor(url=AnyUrl(upload_url), method="POST"),
            )

        return attachment

    async def delete_attachment(self, attachment_id: str, context: dict[str, Any]) -> None:
            """Should delete the attachment metadata and file"""

            raise NotImplementedError("delete_attachment is not implemented ")           