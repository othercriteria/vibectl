# Model API Key Management

This guide explains how to configure API keys for different model providers (OpenAI, Anthropic, and Ollama) when using vibectl.

## Supported Model Providers

vibectl supports the following model providers:

- **OpenAI**: For models like `gpt-4` and `gpt-3.5-turbo`
- **Anthropic**: For models like `claude-3.7-sonnet` and `claude-3.7-opus`
- **Ollama**: For local models like `ollama:llama3`

## Configuration Methods

You can configure API keys in multiple ways, in order of precedence:

1. **Environment variables (Recommended for testing)**:
   ```sh
   export VIBECTL_OPENAI_API_KEY="your-openai-key"
   export VIBECTL_ANTHROPIC_API_KEY="your-anthropic-key"
   export VIBECTL_OLLAMA_API_KEY="your-ollama-key" # If needed
   ```

2. **Environment variable key files**:
   ```sh
   export VIBECTL_OPENAI_API_KEY_FILE="/path/to/openai-key-file"
   export VIBECTL_ANTHROPIC_API_KEY_FILE="/path/to/anthropic-key-file"
   export VIBECTL_OLLAMA_API_KEY_FILE="/path/to/ollama-key-file" # If needed
   ```

3. **Configuration file keys**:
   ```sh
   vibectl config set model_keys.openai "your-openai-key"
   vibectl config set model_keys.anthropic "your-anthropic-key"
   vibectl config set model_keys.ollama "your-ollama-key" # If needed
   ```

4. **Configuration file key paths**:
   ```sh
   vibectl config set model_key_files.openai "/path/to/openai-key-file"
   vibectl config set model_key_files.anthropic "/path/to/anthropic-key-file"
   vibectl config set model_key_files.ollama "/path/to/ollama-key-file" # If needed
   ```

5. **Legacy environment variables (for backward compatibility)**:
   ```sh
   export OPENAI_API_KEY="your-openai-key"
   export ANTHROPIC_API_KEY="your-anthropic-key"
   export OLLAMA_API_KEY="your-ollama-key" # If needed
   ```

## Setting Up Model Keys

### OpenAI Models

To use OpenAI models like `gpt-4` or `gpt-3.5-turbo`:

1. Sign up for an API key at [OpenAI API](https://platform.openai.com/)
2. Configure your key using one of the methods above
3. Select an OpenAI model:
   ```sh
   vibectl config set model gpt-4
   ```

Example:
```sh
# Set key via environment variable
export VIBECTL_OPENAI_API_KEY="sk-abcdef1234567890"

# Or store in a file (more secure)
echo "sk-abcdef1234567890" > ~/.openai-key
chmod 600 ~/.openai-key  # Set proper permissions
vibectl config set model_key_files.openai ~/.openai-key

# Use an OpenAI model
vibectl config set model gpt-4
vibectl get pods
```

### Anthropic Models

To use Anthropic models like `claude-3.7-sonnet` or `claude-3.7-opus`:

1. Sign up for an API key at [Anthropic API](https://console.anthropic.com/)
2. Configure your key using one of the methods above
3. Select an Anthropic model (default is `claude-3.7-sonnet`):
   ```sh
   vibectl config set model claude-3.7-sonnet
   ```

Example:
```sh
# Set key via environment variable
export VIBECTL_ANTHROPIC_API_KEY="sk-ant-abcdef1234567890"

# Or store in a file (more secure)
echo "sk-ant-abcdef1234567890" > ~/.anthropic-key
chmod 600 ~/.anthropic-key  # Set proper permissions
vibectl config set model_key_files.anthropic ~/.anthropic-key

# Use an Anthropic model
vibectl config set model claude-3.7-sonnet
vibectl get pods
```

### Ollama Models

To use local Ollama models:

1. Install [Ollama](https://ollama.ai/)
2. Run Ollama locally with `ollama serve`
3. Pull the model you want to use:
   ```sh
   ollama pull llama3
   ```
4. Configure vibectl to use Ollama model:
   ```sh
   vibectl config set model ollama:llama3
   ```

Example:
```sh
# Start the Ollama server
ollama serve &

# Pull your preferred model
ollama pull llama3

# Configure vibectl to use this model
vibectl config set model ollama:llama3

# Use your local model
vibectl get pods
```

Note: Ollama typically doesn't require an API key for local usage, but if you're using a custom Ollama setup that requires authentication, you can configure a key using the methods described above.

## Checking API Key Configuration

To check which model you're configured to use:
```sh
vibectl config get model
```

To see your full configuration (API keys will be hidden):
```sh
vibectl config show
```

## Security Recommendations

- **Don't store API keys in your shell history**: Use key files whenever possible
- **Set restrictive permissions on key files**: `chmod 600 ~/.your-key-file`
- **Don't commit API keys to version control**: Add key files to your `.gitignore`
- **Prefer environment variable key files** over direct environment variables for security
- **For production deployments**: Use a dedicated service account and rotate keys regularly

## Troubleshooting

If you encounter authentication errors:

1. Verify your API key is valid and not expired
2. Check that you've set the key for the correct provider
3. Ensure proper permissions on key files
4. Try using an environment variable to rule out file reading issues

For missing API key errors, vibectl will show detailed instructions on how to set up your key.
