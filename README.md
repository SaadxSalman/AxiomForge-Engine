# OmniLingua-Agent 🗣️🌍

Building on the OmniLingua-SEA project, this is an advanced agent that not only translates but also generates new, culturally nuanced content (text, audio, video) in dozens of languages. OmniLingua-Agent ensures that content remains culturally relevant and contextually accurate, transcending simple word-for-word translation.

-----

## ✨ Features

  * **Culturally-Aware Generation:** A **Cultural Context Agent** ensures that all generated content is sensitive to and reflective of the target culture's nuances and customs.
  * **Multi-Modal Translation & Generation:** Capable of translating and generating new content in multiple formats, including text, audio, and video.
  * **Emotional Subtext Analysis:** Utilizes a **vision model** to interpret gestures and facial expressions, allowing the agent to understand and respond to the emotional tone of a conversation.
  * **Advanced Cross-Lingual Understanding:** Employs a massive, cross-lingual **embedding model** fine-tuned on a unique dataset to capture subtle linguistic differences.
  * **Seamless User Experience:** The **Next.js** and **tRPC** tech stack ensures a fast, responsive, and real-time user interface.

-----

## ⚙️ Tech Stack

  * **Frontend:** [Next.js](https://nextjs.org/)
  * **Communication:** tRPC
  * **Core Generation Model:** Massive multimodal model
  * **Embeddings:** [Sentence-Transformers](https://www.sbert.net/)
  * **Contextual Retrieval:** Vector database

-----

## 🚀 Getting Started

### Prerequisites

  * Node.js
  * Python 3.10+
  * Access to the massive multimodal model

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/saadsalmanakram/OmniLingua-Agent.git
    cd OmniLingua-Agent
    ```
2.  **Set up the frontend:**
    ```bash
    npm install
    ```
3.  **Configure the backend:**
    Follow the instructions in the `backend/` directory to set up the agent services and connect them to the necessary models.

### Configuration

Create a `.env` file to store your API keys and model credentials.

### Usage

Run the Next.js server and the backend services to start the agent. You can then interact with it via the web interface.

-----

