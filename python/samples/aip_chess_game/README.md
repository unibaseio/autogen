# Chess Game Example

An example with two chess player agents that executes its own tools to demonstrate tool use and reflection on tool use.

## Prerequisites

First, you need a shell with AutoGen core and required dependencies installed.

```bash
pip install git+https://github.com/unibaseio/aip-agent.git
pip install "chess"
cd python/packages/autogen-core
pip install -e .
cd python/packages/autogen-ext
pip install -e .
```

## Model Configuration

The model configuration should defined in a `model_config.yml` file.
Use `model_config_template.yml` as a template.

## Running the example

- MEMBASE_TASK_ID is same
- MEMBASE_ID is different with each other
- MEMBASE_ACCOUNT have balance in bnb testnet

```bash
# start server
export MEMBASE_ID="<membase uuid>"
export MEMBASE_ACCOUNT="<membase account>"
export MEMBASE_SECRET_KEY="<membase secret key>"
python membase_hub.py

# start game board, wait for palyers
export MEMBASE_ID="<membase uuid>"
export MEMBASE_TASK_ID="<this task uuid>"
export MEMBASE_ACCOUNT="<membase account>"
export MEMBASE_SECRET_KEY="<membase secret key>"
python main.py --verbose --role=board

# start player black
export MEMBASE_ID="<membase uuid>"
export MEMBASE_TASK_ID="<this task uuid>"
export MEMBASE_ACCOUNT="<membase account>"
export MEMBASE_SECRET_KEY="<membase secret key>"
python main.py --verbose --role=black --control=<board membase_id>

# start player white
export MEMBASE_ID="<membase uuid>"
export MEMBASE_TASK_ID="<this task uuid>"
export MEMBASE_ACCOUNT="<membase account>"
export MEMBASE_SECRET_KEY="<membase secret key>"
python main.py --verbose --role=white --control=<board membase_id>

# start game
> input white palyer membase_id

# start web browser in localhost:5000, show chess board
python app.py
```
