import React, { useState } from "react";
import Header from "./components/Header";
import CloudSelector from "./components/CloudSelector";
import AWS from "./pages/AWS";
import GCP from "./pages/GCP";
import Azure from "./pages/Azure";

function App() {
  const [selectedCloud, setSelectedCloud] = useState("AWS");

  const renderPage = () => {
    switch (selectedCloud) {
      case "AWS":
        return <AWS />;
      case "GCP":
        return <GCP />;
      case "Azure":
        return <Azure />;
      default:
        return <AWS />;
    }
  };

  return (
    <div>
      <Header />
      <CloudSelector selectedCloud={selectedCloud} setSelectedCloud={setSelectedCloud} />
      {renderPage()}
    </div>
  );
}

export default App;
