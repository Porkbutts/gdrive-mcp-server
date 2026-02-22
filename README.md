# GDrive MCP Server

An MCP (Model Context Protocol) server for the Google Drive API v3. This server allows AI assistants to list, search, read, upload, share, and delete files in Google Drive using OAuth 2.0 authentication.

## Features

- **List files** with pagination, sorting, and folder filtering
- **Search files** using full-text search or raw Google Drive query syntax
- **Read file content** with automatic export for Google Workspace files (Docs, Sheets, Slides)
- **Upload files** from local disk or create new files from text content
- **Create folders** with optional nesting
- **Share files** with users by email (reader, commenter, or writer roles)
- **Delete files** (move to trash or permanently delete)
- **Get file metadata** including permissions, owners, and sharing status

## Prerequisites

- Python 3.10+
- Google Cloud project with Google Drive API enabled
- OAuth 2.0 credentials (Desktop app type)

## Installation

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Configuration

Place your OAuth 2.0 Client ID JSON file at:

```
~/.config/google-drive-mcp/credentials.json
```

Or override the path with environment variables:

```bash
export GDRIVE_CREDENTIALS_PATH=/path/to/credentials.json
export GDRIVE_TOKEN_PATH=/path/to/token.json
```

On first run, a browser window will open for OAuth consent. The token is cached at `~/.config/google-drive-mcp/token.json` for subsequent runs.

## Usage with Claude Code

```bash
claude mcp add-json google-drive '{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/gdrive-mcp-server", "python", "-m", "gdrive_mcp_server.server"]
}'
```

## Available Tools

### gdrive_list_files

List files in Google Drive, optionally within a specific folder.

**Parameters:**
- `page_size`: Number of files to return (1-100, default: 20)
- `page_token`: Token for the next page of results
- `order_by`: Sort order (e.g. `name`, `modifiedTime desc`)
- `folder_id`: List files inside this folder ID
- `include_trashed`: Include trashed files (default: false)

### gdrive_search_files

Search for files by name or content. Supports natural-language terms or raw Drive query syntax.

**Parameters:**
- `query` (required): Search term or raw query (e.g. `"name contains 'budget'"`)
- `page_size`: Max results to return (1-100, default: 20)
- `page_token`: Token for the next page of results

### gdrive_get_file

Get detailed metadata for a specific file including permissions and sharing status.

**Parameters:**
- `file_id` (required): The Google Drive file ID

### gdrive_read_file

Read or export the content of a file. Automatically handles Google Workspace files (Docs -> text, Sheets -> CSV, Slides -> text).

**Parameters:**
- `file_id` (required): The Google Drive file ID
- `export_mime_type`: Export format for Workspace files (e.g. `text/plain`, `text/csv`, `application/pdf`)

### gdrive_upload_file

Upload a local file or create a new file with text content.

**Parameters:**
- `name` (required): File name to create in Drive
- `local_path`: Absolute path to a local file to upload
- `content`: Text content to upload as the file body
- `mime_type`: MIME type (auto-detected if omitted)
- `parent_folder_id`: Parent folder ID (omit for root)

### gdrive_create_folder

Create a new folder in Google Drive.

**Parameters:**
- `name` (required): Folder name
- `parent_folder_id`: Parent folder ID (omit for root)

### gdrive_share_file

Share a file with another user by email.

**Parameters:**
- `file_id` (required): The Google Drive file ID to share
- `email` (required): Email address of the recipient
- `role`: Permission role — `reader`, `commenter`, or `writer` (default: `reader`)
- `send_notification`: Send an email notification (default: true)

### gdrive_delete_file

Delete a file from Google Drive.

**Parameters:**
- `file_id` (required): The Google Drive file ID to delete
- `permanently`: If true, permanently delete (skip trash). Default moves to trash.

## Setup Guide

### Step 1: Create a Google Cloud project

1. Go to https://console.cloud.google.com and create a new project (or select an existing one)
2. Navigate to **APIs & Services > Library**
3. Search for **Google Drive API** and click **Enable**

### Step 2: Create OAuth 2.0 credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. If prompted, configure the **OAuth consent screen** first:
   - Choose **External** user type (or Internal if using Google Workspace)
   - Fill in the required app name and email fields
   - Add scopes: `https://www.googleapis.com/auth/drive`
   - Add your Google account as a **test user**
4. Back in Credentials, create an **OAuth client ID**:
   - Application type: **Desktop app**
   - Name: anything (e.g. "GDrive MCP Server")
5. Click **Download JSON** and save it to `~/.config/google-drive-mcp/credentials.json`

### Step 3: Run the server

```bash
uv run python -m gdrive_mcp_server.server
```

On first run, a browser window will open. Sign in with your Google account and grant Drive access. The refresh token is saved automatically.

### Step 4: Configure the MCP server

Add the server to your Claude Code config (see [Usage with Claude Code](#usage-with-claude-code) above).

## License

MIT
