require('dotenv').config();
const express = require('express');
const { Client } = require('@line/bot-sdk');
const { createClient } = require('@supabase/supabase-js');

const config = {
  channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
  channelSecret: process.env.LINE_CHANNEL_SECRET,
};

const lineClient = new Client(config);
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);

const app = express();
app.use(express.json());

// Webhook handler
app.post('/webhook', async (req, res) => {
  const events = req.body.events;
  if (!events || events.length === 0) {
    return res.status(200).send('No events');
  }
  const results = [];
  for (const event of events) {
    // save raw event to database
    try {
      await supabase.from('messages').insert({
        user_id: event.source && event.source.userId ? event.source.userId : null,
        type: event.type,
        message: event.message || null,
        raw: event,
      });
    } catch (error) {
      console.error('Supabase insert error:', error);
    }

    // simple echo reply for text messages
    if (event.type === 'message' && event.message && event.message.type === 'text') {
      const replyMessage = {
        type: 'text',
        text: '收到：' + event.message.text,
      };
      results.push(lineClient.replyMessage(event.replyToken, replyMessage));
    }
  }

  // execute all replies
  try {
    await Promise.all(results);
  } catch (err) {
    console.error('LINE reply error:', err);
  }
  return res.status(200).end();
});

// health check endpoint
app.get('/', (req, res) => {
  res.send('LINE GPT assistant is running');
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log('Server is running on port', port);
});
