import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/Auth";

const Navbar = () => {
  const { user, signOut } = useAuth();
  
  // console.log(user);

  const navigate = useNavigate();

  async function handleSignOut() {
    try {
      await signOut();
      navigate("/");
    } catch (err) {
      console.log(err.message);
    }
  }

  return (
    <nav className="navbar">
      <h1>SuperPredicto</h1>
      <div className="links">
        <Link to="/"> Home </Link>
        <Link to="/stats"> Stats </Link>
        <Link to="/userpicks"> My Picks </Link>
        <Link to="/makepicks"> Make Picks </Link>
        <Link to="/fixtures"> Scores & Fixtures </Link>
        {user ? (
          <Link to="/">
            <span onClick={handleSignOut}>Logout</span>{" "}
          </Link>
        ) : (
          <Link to="/login">Login</Link>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
