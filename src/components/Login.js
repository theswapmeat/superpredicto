import React, { useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/Auth";

function Login() {
  const emailRef = useRef();
  const passwordRef = useRef();
  const { signIn } = useAuth();
  const { state } = useLocation();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();

    const email = emailRef.current.value;
    const password = passwordRef.current.value;
    const { error } = await signIn({ email, password });

    if (error) {
      console.log(error);
    } else {
      navigate(state?.path || "/");
    }
  };

  return (
    <div>
      <h3> Login test@test.com</h3>
      <input placeholder="Email..." type="email" ref={emailRef} />
      <input placeholder="Password..." type="password" ref={passwordRef} />
      <button onClick={handleSubmit}> Login</button>
      <div>
        Need an account? <Link to="/signup">Sign Up</Link>
      </div>
    </div>
  );
}

export default Login;
