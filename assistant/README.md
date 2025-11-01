# LINE GPT Assistant

This directory contains a Node.js server for a LINE Official Account assistant integrated with GPT and Supabase.

## Requirements

- Node.js 18+
- A LINE Official Account with Messaging API enabled.
- Supabase project for storing messages and attachments.
- OpenAI API key.

## Setup

1. Copy `.env.example` to `.env` and fill in your credentials:

   ```
   LINE_CHANNEL_SECRET=...
   LINE_CHANNEL_ACCESS_TOKEN=...
   SUPABASE_URL=...
   SUPABASE_ANON_KEY=...
   OPENAI_API_KEY=...
   PORT=3000
   ```

2. Install dependencies:

   ```bash
   cd assistant
   npm install
   ```

3. Initialize Supabase:

   - Create tables using the SQL in `db_schema.sql`.

4. Run development server:

   ```bash
   npm run dev
   ```

   The server will listen on the port specified in `.env`.

## Deploy

Use a platform like Vercel, Render, or Railway. Set the same environment variables in the deployment settings.
