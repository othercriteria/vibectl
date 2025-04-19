# Chaos Monkey Overseer Frontend

React frontend for the Chaos Monkey Overseer.

## Features

- Real-time updates using Socket.IO
- Service status dashboard
- Agent logs display
- Kubernetes cluster status visualization
- Built with React for a modern, responsive UI

## Frontend Structure

The frontend is a standard React application:

- `src/` - React components and logic
- `public/` - Static assets
- `package.json` - Dependencies and build configuration

## Development

For development:

1. Install dependencies:
   ```
   npm install
   ```

2. Start the development server:
   ```
   npm start
   ```

3. Run the overseer backend in a separate terminal

The React development server proxies API requests to the backend running on port 8080.

## Building

The frontend is built as part of the overseer Docker image:

```
cd ../
./build.sh
```

This builds both the React frontend and the Python backend into a single Docker image. 