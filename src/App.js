import Home from "./components/Home";
import Navbar from "./components/Navbar";
import Login from "./components/Login";
import Fixtures from "./components/Fixtures";
import MakePicks from "./components/MakePicks";
import PrivateRoute from "./components/PrivateRoute";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "react-query";
import { AuthProvider } from "./contexts/Auth";
import Signup from "./components/Signup";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="container">
        <Router>
          <AuthProvider>
            <Navbar />
            <Routes>
              <Route element={<PrivateRoute />}>
                <Route path="/makepicks" element={<MakePicks />} />
              </Route>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/fixtures" element={<Fixtures />} />
            </Routes>
          </AuthProvider>
        </Router>
      </div>
    </QueryClientProvider>
  );
}

export default App;
