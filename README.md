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

## 🛠️ Tech Stack

* **MERN Stack (Extended):**
    * **M**ongoDB: For persistent data storage.
    * **E**xpress.js: Powering backend API services.
    * **R**eact: Integrated via **Next.js** for high-performance UI.
    * **N**ode.js: The runtime environment for the application.
* **Frontend Enhancements:**
    * **TypeScript:** For robust, type-safe development.
    * **Tailwind CSS:** For modern, utility-first styling.
* **Communication:** tRPC
* **Core Generation Model:** Massive multimodal model
* **Embeddings:** [Sentence-Transformers](https://www.sbert.net/)
* **Contextual Retrieval:** ChromaDB

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

Here is the comprehensive final file structure for **OmniLingua-Agent**. This structure integrates the **Next.js** frontend, **Express** backend, **Python AI Engine**, and **Docker** configurations we've built.

```text
OmniLingua-Agent/
├── apps/
│   ├── web/                         # Frontend (Next.js + Tailwind)
│   │   ├── components/
│   │   │   └── EmotionDashboard.tsx # UI for Vision/Emotion analysis
│   │   ├── pages/
│   │   │   ├── _app.tsx             # tRPC Provider wrapping
│   │   │   └── index.tsx            # Main Landing Page
│   │   ├── utils/
│   │   │   └── trpc.ts              # tRPC Frontend Client logic
│   │   ├── public/                  # Static assets (logos, icons)
│   │   ├── Dockerfile               # Frontend Containerization
│   │   ├── next.config.js
│   │   ├── tailwind.config.js
│   │   └── package.json
│   │
│   └── server/                      # Backend (Node.js + Express)
│       ├── src/
│       │   ├── router.ts            # tRPC Router (Business Logic)
│       │   └── server.ts            # Express Entry point
│       ├── Dockerfile               # Backend Containerization
│       ├── tsconfig.json
│       └── package.json
│
├── packages/
│   ├── ai-engine/                   # AI Layer (Python + FastAPI)
│   │   ├── agent.py                 # Cultural Context & RAG logic
│   │   ├── main.py                  # FastAPI Wrapper
│   │   ├── chroma_db/               # Local Vector Database storage
│   │   ├── Dockerfile               # AI Engine Containerization
│   │   └── requirements.txt         # Python dependencies
│   │
│   └── database/                    # Shared Data Layer
│       └── models/
│           └── Interaction.ts       # Mongoose (MongoDB) Schema
│
├── .env                             # Environment Variables
├── .gitignore                       # Git exclusion rules
├── docker-compose.yml               # Multi-container orchestration
├── package.json                     # Root workspace configuration
└── README.md                        # Project documentation

```

----