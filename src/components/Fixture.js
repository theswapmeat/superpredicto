import React from "react";

// const Fixture = ({ fixture, handleUpdatePick }) => {
//   const { id, matchdate, hometeamname, awayteamname, iscomplete } = fixture;
//   const [hometeamscore, setHometeamscore] = useState(null);
//   const [awayteamscore, setAwayteamscore] = useState(null);
//   const matchDate = new Date(matchdate);

//   // handleUpdatePick({ id, hometeamscore, awayteamscore });

//   return (
//     <>
//       <div className="card">
//         Match {fixture.id} {matchDate.toDateString()}
//         <p>
//           {hometeamname.name} {iscomplete ? "0 - 0" : "v"} {awayteamname.name}
//         </p>
//         <form>
//           <input
//             type="text"
//             placeholder={`${hometeamname.name}'s score`}
//             onChange={(e) => setHometeamscore(e.target.value)}
//           ></input>
//           <input
//             type="text"
//             placeholder={`${awayteamname.name}'s score`}
//             onChange={(e) => setAwayteamscore(e.target.value)}
//           ></input>
//         </form>
//       </div>
//     </>
//   );
// };

const Fixture = ({ date, matches, handleUpdatePick }) => {
  console.log(handleUpdatePick)
  return (
    <>
      <div className="card">
        <h4>{new Date(date).toDateString()}</h4>
        {matches.map((match) => (
          <div key={match.id}>
            <div>
              Match {match.id}
              <p>
                {match.hometeamname.name} {match.iscomplete ? "0 - 0" : "v"}{" "}
                {match.awayteamname.name}
              </p>
            </div>
          </div>
        ))}
      </div>
    </>
  );
};

export default Fixture;
