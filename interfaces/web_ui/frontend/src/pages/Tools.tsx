import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  GitBranch,
  HeartPulse,
  Gauge,
  FileText,
  AudioLines,
  Terminal,
  ArrowRight,
  Wrench,
} from 'lucide-react'

interface ToolDef {
  id: string
  displayName: string
  shortName: string
  description: string
  longDescription: string
  category: 'git' | 'monitoring' | 'benchmark' | 'documentation' | 'synthesis'
  files: number
  icon: React.ElementType
  cliExample: string
  features: string[]
}

const tools: ToolDef[] = [
  {
    id: 'gitpod',
    displayName: 'GitPod — Conventional Commit Message Generator',
    shortName: 'GitPod',
    description: 'Auto-generates conventional commit messages from git diffs using your local LLM.',
    longDescription:
      'Analyzes staged and unstaged changes, groups files by feature area, and generates clean conventional commit messages (feat:, fix:, docs:, etc.) for each group. Can optionally stage all files and commit automatically. Never sends your code to the cloud — everything runs through your local Ollama instance.',
    category: 'git',
    files: 6,
    icon: GitBranch,
    cliExample: 'python -m tools.gitpod.conventional_commit_generator --dry-run',
    features: [
      'Reads git diff and groups changed files by feature area',
      'Generates conventional commit messages per area',
      'Optional auto-stage and commit with --no-dry-run',
      'Uses local LLM — no API keys, no cloud',
    ],
  },
  {
    id: 'logmedic',
    displayName: 'LogMedic — Log Monitor & Crash Auto-Recovery',
    shortName: 'LogMedic',
    description: 'Tails application logs, detects crashes, OOMs, and 500 errors, then auto-restarts dead services.',
    longDescription:
      'A real-time log tailing agent that watches your application logs for fatal patterns (OutOfMemoryError, segfault, HTTP 500 spikes, uncaught exceptions). When a crash is detected, it can automatically restart the offending service via systemd, Docker, or a custom restart command. Includes configurable alert thresholds and backoff to prevent restart loops.',
    category: 'monitoring',
    files: 5,
    icon: HeartPulse,
    cliExample: 'python -m tools.logmedic.logmedic --log /var/log/app.log --restart-cmd "docker restart app"',
    features: [
      'Real-time log tailing with regex pattern matching',
      'Detects OOM, segfaults, 500s, and uncaught exceptions',
      'Auto-restart with configurable backoff strategy',
      'Alert writer for Slack/Discord/webhook notifications',
    ],
  },
  {
    id: 'benchpod',
    displayName: 'BenchPod — Ollama Model Benchmarker',
    shortName: 'BenchPod',
    description: 'Benchmarks every installed Ollama model for tokens/sec, time-to-first-token, and code-generation accuracy.',
    longDescription:
      'Runs standardized inference benchmarks across all locally installed Ollama models. Measures tokens-per-second throughput, time-to-first-token (TTFT) latency, and tests code-generation accuracy with a simple Python challenge. Exports results to JSON and CSV for easy comparison. Helps you pick the right model for latency vs quality tradeoffs.',
    category: 'benchmark',
    files: 6,
    icon: Gauge,
    cliExample: 'python -m tools.benchpod.benchpod --benchmark --generate',
    features: [
      'Tests every installed Ollama model automatically',
      'Measures tokens/sec and time-to-first-token',
      'Code-generation accuracy scoring',
      'Exports to JSON and CSV',
    ],
  },
  {
    id: 'docpod',
    displayName: 'DocPod — Auto-Documentation Engine',
    shortName: 'DocPod',
    description: 'Scans Python projects and auto-generates README files, architecture diagrams, and API docs.',
    longDescription:
      'Walks your Python project tree, extracts module structure, docstrings, class hierarchies, and function signatures. Produces a comprehensive README with architecture overview, dependency graph, and module descriptions. Can also generate Mermaid diagrams showing import relationships between modules.',
    category: 'documentation',
    files: 1,
    icon: FileText,
    cliExample: 'python -m tools.docpod.docpod --src ./my_project --out ./docs',
    features: [
      'Auto-discovers Python module structure',
      'Extracts docstrings and type hints',
      'Generates Markdown README with architecture overview',
      'Creates Mermaid dependency diagrams',
    ],
  },
  {
    id: 'synthpod',
    displayName: 'SynthPod — Multi-Model Response Synthesizer',
    shortName: 'SynthPod',
    description: 'Queries ALL available Ollama models in parallel and synthesizes a single best answer via a judge model.',
    longDescription:
      'The swarm approach to inference: instead of trusting one model, SynthPod sends your prompt to every installed Ollama model simultaneously. It collects all responses with timing and token metadata, then feeds them into a "judge" model (auto-selected as the largest successful model) with a structured synthesis prompt. The judge extracts the strongest points from each response, resolves contradictions, and produces one coherent, polished final answer. Results are saved to JSON for inspection.',
    category: 'synthesis',
    files: 2,
    icon: AudioLines,
    cliExample: 'python -m tools.synthpod.synthpod --prompt "Explain quantum computing"',
    features: [
      'Parallel inference across ALL installed Ollama models',
      'Auto-selects largest successful model as synthesis judge',
      'Resolves contradictions and combines best insights',
      'Saves individual + synthesized responses to JSON',
      'Configurable judge model, timeout, and worker count',
    ],
  },
]

const categoryColors: Record<ToolDef['category'], string> = {
  git: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  monitoring: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  benchmark: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  documentation: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  synthesis: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
}

const categoryLabels: Record<ToolDef['category'], string> = {
  git: 'Git Automation',
  monitoring: 'Monitoring',
  benchmark: 'Benchmarking',
  documentation: 'Documentation',
  synthesis: 'Model Synthesis',
}

export function Tools() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Swarm Tools</h1>
          <p className="text-sm text-muted-foreground">
            {tools.length} autonomous tools built by SimpleSwarm — each with a full unique name describing its function.
          </p>
        </div>
        <Badge variant="outline" className="text-xs">
          <Wrench className="mr-1 h-3 w-3" />
          Auto-generated
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {tools.map((tool) => {
          const Icon = tool.icon
          return (
            <Card key={tool.id} className="flex flex-col">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className="rounded-lg bg-primary/10 p-2">
                      <Icon className="h-5 w-5 text-primary" />
                    </div>
                    <Badge className={`text-xs ${categoryColors[tool.category]}`}>
                      {categoryLabels[tool.category]}
                    </Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">{tool.files} files</span>
                </div>
                <CardTitle className="mt-3 text-base">{tool.displayName}</CardTitle>
                <CardDescription className="text-sm leading-relaxed">
                  {tool.description}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 space-y-4">
                <p className="text-xs text-muted-foreground leading-relaxed">{tool.longDescription}</p>

                <div className="space-y-1.5">
                  <p className="text-xs font-semibold text-foreground">Key Features:</p>
                  <ul className="space-y-1">
                    {tool.features.map((feat, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                        <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-primary" />
                        {feat}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-md bg-muted p-2">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Terminal className="h-3 w-3" />
                    <span className="font-mono text-[10px] truncate">{tool.cliExample}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
