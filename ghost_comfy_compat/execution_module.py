"""Ghost compat: execution module — stubs."""


class IsChangedCache:
    def __init__(self, dynprompt=None, outputs_cache=None):
        pass

    def get(self, node_id):
        return None


def get_output_data(obj, input_data_all, execution_block_cb=None, pre_execute_cb=None):
    return []


def get_input_data(inputs, class_def, unique_id, outputs=None, dynprompt=None, extra_info=None):
    return {}


class CacheSet:
    def __init__(self, *args, **kwargs):
        pass
