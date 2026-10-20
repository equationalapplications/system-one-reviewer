import React from "react";

export const Button = ({ label }: { label: string }) => {
  const onClick = () => console.log(label);
  return <button onClick={onClick}>{label}</button>;
};

function Card(props: { title: string }) {
  return <div>{props.title}</div>;
}
