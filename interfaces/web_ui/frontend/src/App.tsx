import { Routes, Route } from 'react-router-dom'
import { ToastContextProvider } from '@/components/ui/toaster'
import { Layout } from '@/components/layout/Layout'
import { Dashboard } from '@/pages/Dashboard'
import { Chat } from '@/pages/Chat'
import { Swarm } from '@/pages/Swarm'
import { Nodes } from '@/pages/Nodes'
import { Settings } from '@/pages/Settings'
import { OrbStudio } from '@/pages/OrbStudio'
import { SimpleSwarm } from '@/pages/SimpleSwarm'
import { SwarmCoder } from '@/pages/SwarmCoder'
import { Projects } from '@/pages/Projects'
import { Mesh } from '@/pages/Mesh'
import { Tools } from '@/pages/Tools'
import { MeshRemote } from '@/pages/MeshRemote'
import { Marketplace } from '@/pages/Marketplace'
import { Earnings } from '@/pages/Earnings'
import { MyTasks } from '@/pages/MyTasks'

export default function App() {
  return (
    <ToastContextProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/swarm" element={<Swarm />} />
          <Route path="/nodes" element={<Nodes />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/orbstudio" element={<OrbStudio />} />
          <Route path="/simpleswarm" element={<SimpleSwarm />} />
          <Route path="/swarmcoder" element={<SwarmCoder />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/mesh" element={<Mesh />} />
          <Route path="/tools" element={<Tools />} />
          <Route path="/mesh-remote" element={<MeshRemote />} />
          <Route path="/marketplace" element={<Marketplace />} />
          <Route path="/earnings" element={<Earnings />} />
          <Route path="/my-tasks" element={<MyTasks />} />
        </Routes>
      </Layout>
    </ToastContextProvider>
  )
}
