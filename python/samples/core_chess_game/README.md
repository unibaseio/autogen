# Chess Game Example

An example with two chess player agents that executes its own tools to demonstrate tool use and reflection on tool use.

## Prerequisites

First, you need a shell with AutoGen core and required dependencies installed.

```bash
pip install "autogen-agentchat" "autogen-ext[openai,grpc]" "chess"
```

## Model Configuration

The model configuration should defined in a `model_config.yml` file.
Use `model_config_template.yml` as a template.

## Running the example

```bash
# start host
python run_host.py
# start player black
python main.py --verbose --role=black
# start player white
python main.py --verbose --role=white
# start game board
python main.py --verbose --role=board
# start web browser in localhost:5000, show chess board
python app.py
```
