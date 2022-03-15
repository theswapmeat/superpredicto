import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useLocation } from "react-router";
import { useAuth } from "../contexts/Auth";

const PrivateRoute = () => {
//   const auth = null; // determine if authorized, from context or however you're doing it
  const { user } = useAuth();
    console.log("user:", user)
  const location = useLocation();
  console.log(location.pathname)
  // If authorized, return an outlet that will render child elements
  // If not, return element that will navigate to login page
  return user ? (
    <Outlet />
  ) : (
    <Navigate to="/login" replace state={{ path: location.pathname }} />
  );
};

export default PrivateRoute;