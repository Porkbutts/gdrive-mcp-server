#!/usr/bin/env python3
"""
MCP Server for Google Drive API v3.

Provides tools to list, search, read, upload, create, share, and delete
files in Google Drive using OAuth 2.0 authentication.
"""

import os
import io
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_credentials() -> Credentials:
    """Build OAuth 2.0 credentials from environment variables."""
    client_id = os.environ.get("GDRIVE_CLIENT_ID")
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET")
    refresh_token = os.environ.get("GDRIVE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Missing required environment variables. Set all of: "
            "GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN"
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def _drive_service():
    """Return an authenticated Google Drive v3 service client."""
    return build("drive", "v3", credentials=_get_credentials())


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def _handle_error(e: Exception) -> str:
    """Return a user-friendly error string."""
    from googleapiclient.errors import HttpError

    if isinstance(e, HttpError):
        status = e.resp.status
        detail = e._get_reason() if hasattr(e, "_get_reason") else str(e)
        if status == 404:
            return f"Error: File not found. Check that the file ID is correct. ({detail})"
        if status == 403:
            return f"Error: Permission denied. You may not have access to this file. ({detail})"
        if status == 429:
            return "Error: Rate limit exceeded. Wait a moment and try again."
        return f"Error: Google API returned {status}. {detail}"
    if isinstance(e, FileNotFoundError):
        return f"Error: {e}"
    return f"Error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("gdrive_mcp_server")

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class ListFilesInput(BaseModel):
    """Input for listing files."""
    model_config = ConfigDict(str_strip_whitespace=True)

    page_size: Optional[int] = Field(default=20, description="Number of files to return (1-100)", ge=1, le=100)
    page_token: Optional[str] = Field(default=None, description="Token for the next page of results")
    order_by: Optional[str] = Field(default="modifiedTime desc", description="Sort order, e.g. 'name', 'modifiedTime desc'")
    folder_id: Optional[str] = Field(default=None, description="List files inside this folder ID. Omit for root / all files.")
    include_trashed: Optional[bool] = Field(default=False, description="Include trashed files in results")


class SearchFilesInput(BaseModel):
    """Input for searching files."""
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., description="Search query – either a natural-language term (searches fullText) or a raw Drive query string starting with a field name (e.g. \"name contains 'report'\")", min_length=1, max_length=500)
    page_size: Optional[int] = Field(default=20, description="Max results to return (1-100)", ge=1, le=100)
    page_token: Optional[str] = Field(default=None, description="Token for the next page of results")


class GetFileInput(BaseModel):
    """Input for getting file metadata."""
    model_config = ConfigDict(str_strip_whitespace=True)

    file_id: str = Field(..., description="The Google Drive file ID", min_length=1)


class SaveFileInput(BaseModel):
    """Input for saving a Drive file to local disk."""
    model_config = ConfigDict(str_strip_whitespace=True)

    file_id: str = Field(..., description="The Google Drive file ID", min_length=1)
    local_path: str = Field(
        ...,
        description="Local file path to save the downloaded content to.",
        min_length=1,
    )
    export_mime_type: Optional[str] = Field(
        default=None,
        description="For Google Workspace files, the MIME type to export as (e.g. 'text/plain', 'application/pdf', 'text/csv'). Ignored for binary files.",
    )


class UploadFileInput(BaseModel):
    """Input for uploading/creating a file."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="File name to create in Drive", min_length=1, max_length=500)
    local_path: Optional[str] = Field(default=None, description="Absolute path to a local file to upload. Mutually exclusive with 'content'.")
    content: Optional[str] = Field(default=None, description="Text content to upload as file body. Mutually exclusive with 'local_path'.")
    mime_type: Optional[str] = Field(default=None, description="MIME type of the file (auto-detected if omitted)")
    parent_folder_id: Optional[str] = Field(default=None, description="ID of parent folder. Omit for root.")


class CreateFolderInput(BaseModel):
    """Input for creating a folder."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="Folder name", min_length=1, max_length=500)
    parent_folder_id: Optional[str] = Field(default=None, description="Parent folder ID. Omit for root.")


class ShareFileInput(BaseModel):
    """Input for sharing a file."""
    model_config = ConfigDict(str_strip_whitespace=True)

    file_id: str = Field(..., description="The Google Drive file ID to share", min_length=1)
    email: str = Field(..., description="Email address of the person to share with", min_length=3)
    role: str = Field(default="reader", description="Permission role: 'reader', 'commenter', or 'writer'")
    send_notification: Optional[bool] = Field(default=True, description="Send an email notification to the recipient")


class DeleteFileInput(BaseModel):
    """Input for deleting a file."""
    model_config = ConfigDict(str_strip_whitespace=True)

    file_id: str = Field(..., description="The Google Drive file ID to delete", min_length=1)
    permanently: Optional[bool] = Field(default=False, description="If true, permanently delete (skip trash). Default moves to trash.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FILE_FIELDS = "id, name, mimeType, size, modifiedTime, createdTime, owners, parents, webViewLink, trashed"


def _format_file(f: dict) -> str:
    """Format a single file dict into a readable Markdown block."""
    lines = [f"### {f.get('name', 'Untitled')}"]
    lines.append(f"- **ID**: `{f.get('id')}`")
    lines.append(f"- **Type**: {f.get('mimeType', 'unknown')}")
    if f.get("size"):
        size_kb = int(f["size"]) / 1024
        lines.append(f"- **Size**: {size_kb:.1f} KB")
    if f.get("modifiedTime"):
        lines.append(f"- **Modified**: {f['modifiedTime']}")
    if f.get("owners"):
        names = ", ".join(o.get("displayName", o.get("emailAddress", "?")) for o in f["owners"])
        lines.append(f"- **Owner**: {names}")
    if f.get("webViewLink"):
        lines.append(f"- **Link**: {f['webViewLink']}")
    if f.get("trashed"):
        lines.append("- **Trashed**: yes")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gdrive_list_files",
    annotations={
        "title": "List Google Drive Files",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gdrive_list_files(params: ListFilesInput) -> str:
    """List files in Google Drive, optionally within a specific folder.

    Returns a paginated list of files with metadata including name, ID, type,
    size, modified time, and web link.

    Args:
        params: ListFilesInput with page_size, page_token, order_by,
                folder_id, and include_trashed.

    Returns:
        Markdown-formatted list of files with pagination info.
    """
    try:
        service = _drive_service()

        q_parts: list[str] = []
        if params.folder_id:
            q_parts.append(f"'{params.folder_id}' in parents")
        if not params.include_trashed:
            q_parts.append("trashed = false")
        q = " and ".join(q_parts) if q_parts else None

        resp = (
            service.files()
            .list(
                q=q,
                pageSize=params.page_size,
                pageToken=params.page_token,
                orderBy=params.order_by,
                fields=f"nextPageToken, files({FILE_FIELDS})",
            )
            .execute()
        )

        files = resp.get("files", [])
        if not files:
            return "No files found."

        lines = ["# Google Drive Files", ""]
        for f in files:
            lines.append(_format_file(f))
            lines.append("")

        next_token = resp.get("nextPageToken")
        if next_token:
            lines.append(f"---\n*More results available.* Use `page_token`: `{next_token}`")

        return "\n".join(lines)

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_search_files",
    annotations={
        "title": "Search Google Drive Files",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gdrive_search_files(params: SearchFilesInput) -> str:
    """Search for files in Google Drive by name or content.

    Accepts either a natural-language search term (searches fullText) or a raw
    Google Drive query string (e.g. "name contains 'budget'").

    Args:
        params: SearchFilesInput with query, page_size, page_token.

    Returns:
        Markdown-formatted search results with pagination info.
    """
    try:
        service = _drive_service()

        # Heuristic: if the query looks like a raw Drive query, use it directly
        raw_fields = ("name ", "mimeType", "fullText", "modifiedTime", "trashed", "'")
        if any(params.query.startswith(rf) for rf in raw_fields):
            q = params.query
        else:
            escaped = params.query.replace("\\", "\\\\").replace("'", "\\'")
            q = f"fullText contains '{escaped}' and trashed = false"

        resp = (
            service.files()
            .list(
                q=q,
                pageSize=params.page_size,
                pageToken=params.page_token,
                fields=f"nextPageToken, files({FILE_FIELDS})",
            )
            .execute()
        )

        files = resp.get("files", [])
        if not files:
            return f"No files found matching '{params.query}'."

        lines = [f"# Search Results for '{params.query}'", f"Showing {len(files)} result(s)", ""]
        for f in files:
            lines.append(_format_file(f))
            lines.append("")

        next_token = resp.get("nextPageToken")
        if next_token:
            lines.append(f"---\n*More results available.* Use `page_token`: `{next_token}`")

        return "\n".join(lines)

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_get_file",
    annotations={
        "title": "Get File Metadata",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gdrive_get_file(params: GetFileInput) -> str:
    """Get detailed metadata for a specific file by its ID.

    Args:
        params: GetFileInput with file_id.

    Returns:
        Markdown-formatted file metadata.
    """
    try:
        service = _drive_service()
        f = (
            service.files()
            .get(
                fileId=params.file_id,
                fields=f"{FILE_FIELDS}, description, starred, shared, permissions",
            )
            .execute()
        )

        lines = ["# File Details", "", _format_file(f)]

        if f.get("description"):
            lines.append(f"- **Description**: {f['description']}")
        if f.get("createdTime"):
            lines.append(f"- **Created**: {f['createdTime']}")
        lines.append(f"- **Starred**: {'yes' if f.get('starred') else 'no'}")
        lines.append(f"- **Shared**: {'yes' if f.get('shared') else 'no'}")

        perms = f.get("permissions", [])
        if perms:
            lines.append("")
            lines.append("#### Permissions")
            for p in perms:
                display = p.get("emailAddress", p.get("displayName", p.get("id", "?")))
                lines.append(f"- {display} — **{p.get('role', '?')}**")

        return "\n".join(lines)

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_save_file",
    annotations={
        "title": "Save File to Local Disk",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gdrive_save_file(params: SaveFileInput) -> str:
    """Download a file from Google Drive and save it to a local path.

    For Google Workspace files (Docs, Sheets, Slides), specify export_mime_type
    to choose the export format. Common values:
      - Google Docs  -> 'text/plain', 'text/markdown', 'application/pdf'
      - Google Sheets -> 'text/csv', 'application/pdf'
      - Google Slides -> 'text/plain', 'application/pdf'
      - Google Drawings -> 'image/png'

    For regular files (PDFs, images, etc.), the raw content is downloaded as-is.

    After saving, use your local file-reading tools to read the content.

    Args:
        params: SaveFileInput with file_id, local_path, and optional export_mime_type.

    Returns:
        A confirmation message with the saved file path and size.
    """
    try:
        service = _drive_service()

        meta = service.files().get(fileId=params.file_id, fields="mimeType, name").execute()
        mime = meta.get("mimeType", "")
        name = meta.get("name", "unknown")

        google_workspace_types = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
            "application/vnd.google-apps.drawing": "image/png",
        }

        if mime in google_workspace_types:
            export_mime = params.export_mime_type or google_workspace_types[mime]
            content = service.files().export(fileId=params.file_id, mimeType=export_mime).execute()
        else:
            content = service.files().get_media(fileId=params.file_id).execute()

        if isinstance(content, str):
            content = content.encode("utf-8")

        local_path = os.path.expanduser(params.local_path)
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)

        with open(local_path, "wb") as f:
            f.write(content)

        size = len(content)
        return f"Saved '{name}' to {local_path} ({size:,} bytes)"

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_upload_file",
    annotations={
        "title": "Upload or Create a File",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def gdrive_upload_file(params: UploadFileInput) -> str:
    """Upload a local file or create a new file with text content in Google Drive.

    Provide either `local_path` (to upload an existing file) or `content`
    (to create a new text file). If both are omitted, an empty file is created.

    Args:
        params: UploadFileInput with name, local_path or content,
                optional mime_type and parent_folder_id.

    Returns:
        Markdown summary of the created file.
    """
    try:
        if params.local_path and params.content:
            return "Error: Provide either 'local_path' or 'content', not both."

        service = _drive_service()
        file_metadata: dict = {"name": params.name}
        if params.parent_folder_id:
            file_metadata["parents"] = [params.parent_folder_id]

        media = None
        if params.local_path:
            if not os.path.isfile(params.local_path):
                return f"Error: Local file not found: {params.local_path}"
            media = MediaFileUpload(params.local_path, mimetype=params.mime_type, resumable=True)
        elif params.content:
            mime = params.mime_type or "text/plain"
            media = MediaIoBaseUpload(
                io.BytesIO(params.content.encode("utf-8")),
                mimetype=mime,
                resumable=True,
            )

        created = (
            service.files()
            .create(body=file_metadata, media_body=media, fields=FILE_FIELDS)
            .execute()
        )

        return f"File created successfully.\n\n{_format_file(created)}"

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_create_folder",
    annotations={
        "title": "Create a Folder",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def gdrive_create_folder(params: CreateFolderInput) -> str:
    """Create a new folder in Google Drive.

    Args:
        params: CreateFolderInput with name and optional parent_folder_id.

    Returns:
        Markdown summary of the created folder.
    """
    try:
        service = _drive_service()
        metadata: dict = {
            "name": params.name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if params.parent_folder_id:
            metadata["parents"] = [params.parent_folder_id]

        folder = service.files().create(body=metadata, fields=FILE_FIELDS).execute()
        return f"Folder created successfully.\n\n{_format_file(folder)}"

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_share_file",
    annotations={
        "title": "Share a File",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gdrive_share_file(params: ShareFileInput) -> str:
    """Share a Google Drive file with another user by email.

    Supported roles: 'reader', 'commenter', 'writer'.

    Args:
        params: ShareFileInput with file_id, email, role, send_notification.

    Returns:
        Confirmation message with the permission details.
    """
    try:
        valid_roles = ("reader", "commenter", "writer")
        if params.role not in valid_roles:
            return f"Error: role must be one of {valid_roles}."

        service = _drive_service()
        permission = {"type": "user", "role": params.role, "emailAddress": params.email}

        result = (
            service.permissions()
            .create(
                fileId=params.file_id,
                body=permission,
                sendNotificationEmail=params.send_notification,
                fields="id, role, emailAddress",
            )
            .execute()
        )

        return (
            f"File shared successfully.\n"
            f"- **Email**: {result.get('emailAddress', params.email)}\n"
            f"- **Role**: {result.get('role')}\n"
            f"- **Permission ID**: `{result.get('id')}`"
        )

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="gdrive_delete_file",
    annotations={
        "title": "Delete a File",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gdrive_delete_file(params: DeleteFileInput) -> str:
    """Delete a file from Google Drive.

    By default moves the file to trash. Set permanently=true to skip trash
    and permanently delete (cannot be undone).

    Args:
        params: DeleteFileInput with file_id and optional permanently flag.

    Returns:
        Confirmation message.
    """
    try:
        service = _drive_service()

        if params.permanently:
            service.files().delete(fileId=params.file_id).execute()
            return f"File `{params.file_id}` permanently deleted."
        else:
            service.files().update(fileId=params.file_id, body={"trashed": True}).execute()
            return f"File `{params.file_id}` moved to trash."

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _run_auth_flow():
    """Run interactive OAuth flow to obtain a refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = os.environ.get("GDRIVE_CLIENT_ID")
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Error: Set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET environment variables first.")
        raise SystemExit(1)

    extra = os.environ.get("GDRIVE_EXTRA_SCOPES", "")
    extra_scopes = [s.strip() for s in extra.split(",") if s.strip()]
    scopes = SCOPES + extra_scopes

    print(f"Requesting scopes: {', '.join(scopes)}\n")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes)
    creds = flow.run_local_server(port=0)

    print("\nAuth successful! Set this environment variable:\n")
    print(f"  GDRIVE_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    import sys

    if "--auth" in sys.argv:
        _run_auth_flow()
    else:
        mcp.run()
