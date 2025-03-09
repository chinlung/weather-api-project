# Taiwan Weather MCP Server

A Model Context Protocol (MCP) server that provides Taiwan weather forecasts and alerts data from the Central Weather Administration (CWA) for integration with Claude Desktop.

## Features

- Query Taiwan weather forecasts by location
- Get active weather warnings across Taiwan
- Access rainfall data from weather stations
- View current weather observations by location

## Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) package manager
- [CWA API key](https://opendata.cwa.gov.tw/user/authkey)

## Installation

1. Clone or download this repository
2. Install dependencies using uv:

```bash
cd weather
uv pip install -r requirements.txt
```

3. Configure your CWA API key in the `.env` file:

```
CWA_API_KEY=your_api_key_here
```

## Running the Server

The server can be started with uv:

```bash
uv --directory /Users/scl/PycharmProjects/pythonProject/weather run server.py
```

## Configuring Claude Desktop

Claude Desktop can be configured to use this MCP server by adding the following to your Claude Desktop configuration (`config.json`):

```json
"mcpServers": {
  "taiwan-weather": {
    "command": "/Users/scl/.local/bin/uv",
    "args": [
      "--directory",
      "/Users/scl/PycharmProjects/pythonProject/weather",
      "run",
      "server.py"
    ]
  }
}
```

This configuration will:
1. Use your local `uv` installation to run the server
2. Set the working directory to your project folder
3. Start the MCP server using `server.py`

## Example Queries

Once configured, you can ask Claude Desktop questions like:

- "台北市今天的天氣預報是什麼?"
- "目前台灣有哪些天氣警報?"
- "高雄市的降雨量是多少?"
- "台中市的目前氣象觀測數據"

## How it Works

This server implements the [Model Context Protocol](https://modelcontextprotocol.io/), which allows Claude Desktop to query external APIs through a standardized interface. When you ask Claude about Taiwan weather, it will:

1. Recognize the need for external weather data
2. Send a structured request to the MCP server
3. Receive the weather data
4. Present it back to you in a human-readable format

## Data Source

All weather data is from the [Central Weather Administration Open Data Platform](https://opendata.cwa.gov.tw/dist/opendata-swagger.html).

## Parameters

The MCP server accepts the following parameters:

- `query_type` (required): One of "forecast", "warnings", "rainfall", or "observation"
- `location` (optional): A location name in Taiwan, such as "Taipei" or "Kaohsiung"
- `element` (optional): A specific weather element to filter by

## Troubleshooting

If you encounter issues:

1. Make sure your CWA API key is correctly set in the `.env` file
2. Verify that the working directory path in Claude Desktop's configuration matches your actual project location

## License

MIT