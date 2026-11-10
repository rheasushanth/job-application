"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ResumeReview } from "@/components/resume-review";
import { Callout, PageHeader, Spinner, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { ParsedResume } from "@/lib/types";

const MAX_MB = 10;
const ACCEPT = ".pdf,.docx";

export default function UploadPage() {
  return (
    <AppShell>
      <UploadFlow />
    </AppShell>
  );
}

function UploadFlow() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [parsed, setParsed] = useState<ParsedResume | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  async function handleFile(file: File) {
    setError(null);

    const name = file.name.toLowerCase();
    if (!name.endsWith(".pdf") && !name.endsWith(".docx")) {
      setError("Only PDF and DOCX files are supported.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`That file is larger than ${MAX_MB} MB.`);
      return;
    }
    if (file.size === 0) {
      setError("That file is empty.");
      return;
    }

    setBusy(true);
    try {
      setParsed(await api.resumes.upload(file));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Upload failed. Check your connection and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (parsed) {
    return (
      <ResumeReview
        parsed={parsed}
        onConfirmed={() => router.push("/dashboard?discover=1")}
        onReplace={() => {
          setParsed(null);
          setError(null);
        }}
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Upload your resume"
        description="Text is extracted and structured into a profile. Nothing is used for matching until you have reviewed and confirmed it."
      />

      <div className="mx-auto max-w-prose">
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          className={cx(
            "flex flex-col items-center border border-dashed px-6 py-16 text-center transition-colors",
            dragging ? "border-ink-200 bg-ink-850" : "border-ink-600 bg-ink-900",
          )}
        >
          {busy ? (
            <>
              <Spinner />
              <p className="mt-4 text-sm text-ink-100">Reading your resume</p>
              <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-ink-400">
                Extracting text, identifying sections and structuring your
                skills, education, projects and experience.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm text-ink-100">
                Drop your resume here, or choose a file
              </p>
              <p className="mt-1.5 text-xs text-ink-400">
                PDF or DOCX, up to {MAX_MB} MB
              </p>
              <button
                type="button"
                className="btn-primary mt-6"
                onClick={() => inputRef.current?.click()}
              >
                Choose file
              </button>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) handleFile(file);
                  event.target.value = "";
                }}
              />
            </>
          )}
        </div>

        {error ? (
          <div className="mt-4">
            <Callout tone="danger" title="Upload failed">
              {error}
            </Callout>
          </div>
        ) : null}

        <div className="mt-8 space-y-3 text-xs leading-relaxed text-ink-500">
          <p>
            <span className="text-ink-300">Text-based files only.</span> A
            scanned or photographed resume has no extractable text — export a
            text-based PDF from your editor instead.
          </p>
          <p>
            <span className="text-ink-300">Your file stays private.</span> It is
            stored under a random filename, is readable only by your account,
            and you can delete it at any time from Settings.
          </p>
        </div>
      </div>
    </>
  );
}
