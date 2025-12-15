class Command:
    def do(self, input_file_path: str, output_dir: str, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement this method")