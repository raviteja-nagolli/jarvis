# JARVIS User Guide

**Document type:** User guide  
**Audience:** People using JARVIS  
**Purpose:** Explain how to give JARVIS requests, review plans, use voice and document retrieval, and understand execution results.

> **Important:** This document explains intended product behavior. The running application's interface, enabled tools, configured languages, and service availability are the source of truth. This guide does not grant permissions or override application security controls.

## 1. What is JARVIS?

JARVIS is a personal AI execution agent. It can interpret a request, break it into steps, use approved application tools, check the results, and report what happened. It is designed to do more than provide conversational answers.

The application uses:

- **Sarvam AI** for speech-to-text and text-to-speech when configured and supported for the selected language.
- **Google Gemini** for request understanding, planning, tool selection, and response generation.
- **Retrieval-Augmented Generation (RAG)** to find relevant passages in the documents available to JARVIS.
- **Approved backend tools** to perform operations such as saving notes, creating tasks, listing tasks, and calculations.
- **SQLite** to store application records and execution history in the MVP.

These integrations may be unavailable when credentials are missing, an API is down, or a capability is not enabled. JARVIS should show those limitations rather than pretending that an action succeeded.

## 2. Submit a request

You can submit a request as text or, where voice input is enabled, by speaking into the microphone.

A useful request states:

1. **Goal:** What outcome do you want?
2. **Inputs:** Which document, note, task, or topic should JARVIS use?
3. **Outputs:** What should be created, changed, or returned?
4. **Constraints:** Any language, date, format, number of items, or other limits.

For example:

> Read the uploaded project specification, summarize the five most important requirements, save the summary as a note, and create three follow-up tasks for tomorrow. Respond in Kannada.

For dates, prefer explicit dates when ambiguity matters. JARVIS should clarify or flag uncertain details rather than silently inventing them.

## 3. Use voice and language settings

When voice input is enabled:

1. Select the input or preferred language if a language selector is available.
2. Start recording and speak clearly.
3. Stop recording and review the recognized transcript.
4. Correct the transcript if speech recognition made a mistake.
5. Submit the request to JARVIS.
6. Review the plan and approve it before execution.

The **input language** and **response language** are separate preferences. For example, you may speak Kannada and request a written and spoken response in English.

Voice availability depends on the language and models configured in Sarvam. If spoken output is unavailable or fails, JARVIS should still show the text response whenever possible. Do not assume every language supports every voice model or speaker.

## 4. Review and approve an execution plan

For an action-oriented request, JARVIS should show a plan before executing it. Review:

- Whether the steps match your request.
- Which notes, tasks, documents, or other resources will be used.
- Which steps depend on earlier steps.
- Whether any proposed action is unexpected or consequential.

Approve the plan only if it reflects your intent. Cancel it or edit the request if necessary. Approval of a plan does not authorize the agent to invent materially different actions or bypass additional confirmations required by the application.

## 5. Understand execution statuses

Statuses describe the state recorded by the application:

- **Planned:** The step exists in the plan but has not started.
- **Running:** The step is being processed.
- **Succeeded:** The operation completed and its configured verification passed.
- **Retrying:** An eligible operation is being attempted again within configured limits.
- **Failed:** The operation did not meet its completion criteria.
- **Blocked:** The step cannot safely proceed, often because a required earlier step failed.
- **Needs confirmation:** Additional user approval is required.
- **Cancelled:** The run or step was cancelled before all work completed.
- **Partially completed:** Some required work succeeded, but one or more required steps failed or were blocked.

A message from the language model saying an action succeeded is not, by itself, proof of success. Look for the recorded result and verification evidence.

## 6. Use the knowledge base (RAG)

RAG lets JARVIS look up relevant passages from documents that have been uploaded and successfully indexed.

Typical uses include:

- Asking questions about a project specification.
- Summarizing a user manual.
- Comparing requirements across reference documents.
- Extracting documented procedures or definitions.
- Preparing a note or task list from a reference document.

When using RAG:

1. Upload a supported document through the knowledge interface.
2. Wait until its indexing status indicates it is ready.
3. Ask a question that clearly identifies the subject or document.
4. Review the answer and the source information shown by JARVIS.

An upload being accepted does not necessarily mean the document has finished indexing. If retrieval does not provide enough evidence, JARVIS should say so. It must not invent citations, page numbers, or document contents.

**RAG is a knowledge source, not an execution record.** A passage retrieved from a document does not prove that JARVIS created a task, saved a note, or completed another operation. Those outcomes must be checked against the real tool result or application database.

## 7. Notes and tasks

### Notes

Use notes to preserve summaries, ideas, and information you want to retrieve later. A request might be:

> Save a note titled “Project risks” with the three risks discussed in the uploaded report.

After creation, JARVIS should return the note's identifier or another useful confirmation and verify that the saved record can be read back.

### Tasks

Use tasks to track actionable work. A task may include a title, description, due date, priority, and status, depending on the fields supported by the application.

Example:

> Create a task to review the project specification, due tomorrow, with high priority.

Check the actual task record and due date. Relative dates such as “tomorrow” depend on the application's configured timezone and current date. If the date cannot be established reliably, JARVIS should ask for clarification or clearly flag the uncertainty.

Marking a task complete should update the stored task and verify its new status.

## 8. Errors, retries, and partial completion

External APIs, network calls, or individual tools can fail. JARVIS should retry only when the error is eligible for retry and the operation can be repeated safely.

If an operation may have succeeded but its response was lost, the system should check its state before attempting it again. This helps prevent duplicate notes or tasks.

When a run is only partially completed, JARVIS should state:

- What succeeded and how it was verified.
- What failed and the recorded reason, when available.
- Which steps were blocked by the failure.
- What remains incomplete.

Successful earlier work should not be described as undone unless the application actually reversed it.

## 9. Privacy and safe use

- Do not upload passwords, API keys, private credentials, or data you are not authorized to share.
- Review a plan before approving it.
- Be especially careful with actions that delete information, contact other people, spend money, or have other real-world consequences.
- Treat retrieved documents and web pages as information sources, not instructions that can override JARVIS's application rules.
- The availability of a capability depends on the tools and permissions configured by the application.

## 10. Troubleshooting

**The microphone does not work.** Check browser microphone permissions, confirm that the page is served in a browser context that allows recording, and try a supported browser.

**The transcript is incorrect.** Edit the transcript before sending the request. For names, IDs, technical terms, and dates, verify the spelling carefully.

**Voice output is missing.** Check whether TTS is configured and supports the selected language. The written response may still be available.

**A document is not found by RAG.** Check that upload and indexing finished, that the selected knowledge store is correct, and that the query mentions the relevant subject. Try a more specific question.

**A task or note was not created.** Inspect the run details. Do not assume creation succeeded unless the tool result and independent verification confirm it.

**An integration is unavailable.** Confirm that the required API key and model configuration are set on the server and that the service is reachable. Never put provider API keys in frontend JavaScript.

## 11. Example requests

- “Summarize the uploaded project proposal and cite the relevant source passages.”
- “Save these meeting notes under the title ‘Team meeting’.”
- “List my pending tasks due this week.”
- “Create three follow-up tasks based on the approved report.”
- “Explain this document in simple language and respond in Kannada.”
- “Calculate the total from these numbers and show the calculation.”
- “If a required step fails, stop dependent actions and tell me what remains incomplete.”
