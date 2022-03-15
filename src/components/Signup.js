import React, { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/Auth";
import supabase from "../utils/supabase";

const Signup = () => {
  // const fnameRef = useRef();
  // const lnameRef = useRef();
  const emailRef = useRef();
  const passwordRef = useRef();
  const confirmPasswordRef = useRef();
  const nicknameRef = useRef();
  const [error, setError] = useState("");

  const { signUp } = useAuth();

  let navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    const email = emailRef.current.value;
    const password = passwordRef.current.value;
    const nickname = nicknameRef.current.value;

    setError("");

    if (passwordRef.current.value !== confirmPasswordRef.current.value) {
      return setError("Passwords do not match");
    }

    try {
      const { user } = await signUp(
        // fnameRef.current.value,
        // lnameRef.current.value,
        { email, password }
      );

      await supabase
        .from("profiles")
        .upsert({ id: user.id, username: email, nickname: nickname });

      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <div>
        <h2>Signup</h2>
        <div>{error}</div>
        <form onSubmit={handleSubmit}>
          {/* <input type="text" placeholder="First Name" ref={fnameRef} />
          <input type="text" placeholder="Last Name" ref={lnameRef} /> */}
          <input type="text" placeholder="Nickname" ref={nicknameRef} />
          <input type="email" placeholder="Email address" ref={emailRef} />
          <input type="password" placeholder="Password" ref={passwordRef} />
          <input
            type="password"
            placeholder="Confirm Password"
            ref={confirmPasswordRef}
          />

          <div>
            <button variant="primary" type="Submit">
              Sign up
            </button>
          </div>
        </form>
      </div>
      <div>
        Already have an account? <Link to="/login">Log In</Link>
      </div>
    </>
  );
};

export default Signup;
