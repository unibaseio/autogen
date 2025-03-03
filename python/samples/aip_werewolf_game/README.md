# Werewoves Game Example

An example werewolves game.

## Prerequisites

First, you need a shell with AutoGen core and required dependencies installed.

```bash
pip install git+https://github.com/unibaseio/aip-agent.git
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

# start moderator, wait for palyers
export MEMBASE_ID="<membase uuid>"
export MEMBASE_TASK_ID="<this task uuid>"
export MEMBASE_ACCOUNT="<membase account>"
export MEMBASE_SECRET_KEY="<membase secret key>"
python main.py --verbose

# start six player, run six times
export MEMBASE_ID="<membase uuid>"
export MEMBASE_TASK_ID="<this task uuid>"
export MEMBASE_ACCOUNT="<membase account>"
export MEMBASE_SECRET_KEY="<membase secret key>"
python role.py --verbose --moderator=<moderator membase_id>


# game begins
```
